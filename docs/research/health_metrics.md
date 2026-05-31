# Historical Health Metrics Investigation

Date:
- 2026-05-26
- updated 2026-05-27 with live selector probing for pressure and HRV history
- updated 2026-05-28 with fresh retention and gap-recovery checks
- updated 2026-05-30 with fresh sleep-history revalidation
- updated 2026-05-30 with fresh blood-pressure path revalidation

## Goal

Determine whether the H59 actually exposes historical sleep and health metrics, or whether the current sync was simply not querying the correct protocol surfaces.

Additional local artifact:
- `misc/artifacts/h59_hrv_pressure_probe_20260527.json`

## Summary

The current sync was incomplete.

What is now proven:
- sleep payloads are available on the Big Data service
- historical blood oxygen is available
- historical pressure/stress-like data is available
- historical HRV data is available
- active blood-pressure measurement capture is available
- older-than-today pressure history is available
- older-than-today HRV history is available
- a fresh 7-day backfill query recovered all available history back to the device's first-use date

What remains unresolved:
- historical blood-pressure backfill

## Findings

### Sleep

Result:
- the older UART sleep command path did not produce usable data
- the secondary Big Data service returned structured sleep history
- fresh one-shot syncs on 2026-05-30, against brand-new databases, returned only the latest sleep night plus one ambiguous alternate block
- those fresh syncs produced the same result in both `device_clock=utc` and `device_clock=local` modes
- the older database appeared to contain several nights because it accumulated one current-night payload across several different sync days
- the current sync implementation queries sleep once per sync, outside the per-day backfill loop used for heart rate and activity
- the current client sleep parser and the older legacy probe parser disagree on how `bytes_used` should be interpreted, which means sleep payload field semantics are still not final

Assessment:
- sleep is available
- the correct transport is the secondary Big Data service
- true multi-night backfill from a single proven request is not established yet
- the current evidence is more consistent with "latest sleep night only" than with "full sleep history backfill"
- there is still a parser/packet-alignment risk around `days_ago` and `bytes_used`

### Blood Oxygen / SpO2

Result:
- realtime requests produced valid replies with zero values
- the secondary Big Data service returned historical oxygen samples

Assessment:
- historical SpO2 is available
- the current realtime path is not sufficient

### Pressure / Stress-like History

Result:
- UART command `0x37` returned a valid historical split response
- the values look like a vendor score series rather than a raw measurement
- across the captured databases, `pressure_samples` stay in a narrow `21..65` range at a fixed `30`-minute cadence, which is consistent with a stress-like score and not with systolic/diastolic BP
- the device capability response exposes `support_pressure` and `support_blood_pressure` as separate flags, which strongly suggests that this historical `0x37` stream is not the blood-pressure feature
- live probing on 2026-05-27 showed that the first request byte is a selector:
  - `0` returns a partial current-day series
  - `1` and `2` return fuller older-day series
  - `3` returns an older partial day
  - `4` and above returned explicit no-data on this bracelet
- adding a second request byte had no effect on the returned dataset

Assessment:
- historical pressure/stress-like data is available
- the current sync bug is that it always sends selector `0`, so it only captures today
- the first request byte should be treated as a day/history selector, not a fixed constant

### HRV History

Result:
- UART command `0x39` returned a valid historical split response
- the payload looks like a 16-bit series rather than single-byte samples
- live probing on 2026-05-27 showed the same selector pattern as pressure:
  - `0` returns a partial current-day series
  - `1` and `2` return fuller older-day series
  - `3` returns an older partial day
  - `4` and above returned explicit no-data on this bracelet
- adding a second request byte had no effect on the returned dataset

Assessment:
- historical HRV is available
- the decoder still needs refinement
- the current sync bug is that it always sends selector `0`, so it only captures today
- the first request byte should be treated as a day/history selector, not a fixed constant

### Blood Pressure

Result:
- capability flags and settings indicate support
- the direct `0x69 / dataType=2` realtime path did not produce usable systolic/diastolic values
- direct timestamped `0x14` historical probes produced no responses during the 2026-05-27 live test
- `0x69` data requests for blood pressure only acknowledged with zero-valued `0x69` responses
- a fresh live probe on 2026-05-30 still produced no `cmd 20` blood-pressure history packets
- a full review of the `raw_packets` captured by normal `sync` on 2026-05-31 showed only these historical command ids:
  - `1`, `3`, `21`, `22`, `39`, `42`, `47`, `55`, `57`, `67`
- the only unmapped historical response was a fixed one-packet `0x2f` reply (`2ff40000000000000000000000000023`) once per sync; it carries no timestamped series structure and does not resemble paired BP values
- no captured database, including archived pre-reset databases, contains any `command_id=20` raw packet at all
- a fresh live probe on 2026-05-30 confirmed that `0x69 / dataType=2` exposes only a live cuff-pressure-like value in bytes `6..7`
- a fresh live probe on 2026-05-30 confirmed that `0x69 / dataType=5` (`HealthCheck`) emits the final blood-pressure result near the end of the measurement window
- decoded `HealthCheck` packet layout:
  - byte `3`: diastolic
  - byte `4`: systolic
  - byte `5`: heart rate
  - bytes `6..7`: live cuff-pressure-like value in tenths
- example final packet captured live:
  - `690500436f48a9030000000000000014`
  - decoded as `diastolic=67`, `systolic=111`, `heart_rate=72`, `cuff_pressure_tenths=937`
- a live end-to-end sync on 2026-05-30 with `--realtime health-check` persisted realtime observations that can be denormalized into a paired BP reading

Assessment:
- active blood-pressure measurement is now proven and decoded through `HealthCheck`
- the local data model now stores separate systolic and diastolic values
- the direct `dataType=2` path should be treated as a lower-level cuff-pressure stream, not as a finished BP reading
- the normal historical sync payload currently shows no hidden paired-BP stream waiting to be decoded
- historical blood-pressure backfill is still unresolved

### History Retention and Gap Recovery

Result:
- on 2026-05-28, a fresh initial backfill queried 7 days and recovered history back to `2026-05-24`
- that date matches the start of actual device use, so the result is consistent with the bracelet retaining about 7 days of full history
- this does not directly prove a hard 7-day retention ceiling yet; it shows that a 7-day query works and that all stored days since first use were returned
- fresh one-day and fresh backfill syncs reproduced the same heart-rate and activity gaps in new databases
- those gaps therefore were present in the bracelet's accessible history at sync time

Examples:
- heart-rate gaps on `2026-05-27` included `18:25 -> 19:10 UTC` and `19:10 -> 20:30 UTC`
- heart-rate gaps on `2026-05-28` included `08:45 -> 10:50 UTC` and `12:40 -> 14:45 UTC`
- the same gaps were observed after a fresh backfill into a new database, so they were not caused by local overwrite behavior

Assessment:
- the bracelet appears to keep about 7 days of accessible history, though that remains an inference until older real usage data exists
- historical reads appear non-destructive
- currently missing intervals cannot be recovered if the bracelet itself no longer returns them during a fresh pull

## Practical Conclusion

The missing pressure and HRV history were not mainly a “not enough history” problem.

The primary issue was that the CLI only queried:
- battery
- heart-rate settings
- capabilities
- heart-rate history
- activity history
- optional realtime metrics

It did not query:
- the secondary Big Data service
- legacy historical pressure
- legacy historical HRV

It also used the wrong request shape for pressure and HRV history:
- it always sent selector `0`
- it never iterated older selectors even though the bracelet exposes different historical datasets on selectors `1`, `2`, and `3`

The later retention check adds two important conclusions:
- the bracelet can answer a 7-day history query and returned all stored history back to first use
- the remaining gaps seen in fresh databases are device-side history gaps, not artifacts introduced by the local sync process

Sleep is narrower than pressure and HRV:
- the Big Data sleep path is real and should be kept
- but the current evidence does not prove that one sync can backfill several older nights
- if more than the latest night is required, the remaining work is sleep-specific reverse engineering rather than simple loop expansion

## Next Implementation Steps

1. Update `read_pressure_history_packet()` and `read_hrv_history_packet()` so the first request byte is a selector parameter instead of a hard-coded `0`.
2. Iterate selectors during backfill and incremental sync until the device returns `0xFF` no-data.
3. Keep the secondary Big Data transport for sleep and blood oxygen.
4. Refine the HRV decoder to 16-bit sample parsing and trim trailing empty slots correctly.
5. Investigate historical blood pressure separately from the active `HealthCheck` measurement path.
6. Reconcile the current sleep parser with the older probe parser and revalidate `days_ago` / `bytes_used` semantics.
7. Check whether the Big Data sleep request supports a history selector or alternate request shape for older nights.
