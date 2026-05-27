# Historical Health Metrics Investigation

Date:
- 2026-05-26
- updated 2026-05-27 with live selector probing for pressure and HRV history

## Goal

Determine whether the H59 actually exposes historical sleep and health metrics, or whether the current sync was simply not querying the correct protocol surfaces.

Additional local artifact:
- `misc/artifacts/h59_hrv_pressure_probe_20260527.json`

## Summary

The current sync was incomplete.

What is now proven:
- sleep history is available
- historical blood oxygen is available
- historical pressure/stress-like data is available
- historical HRV data is available
- older-than-today pressure history is available
- older-than-today HRV history is available

What remains unresolved:
- historical blood pressure

## Findings

### Sleep

Result:
- the older UART sleep command path did not produce usable data
- the secondary Big Data service returned structured sleep history

Assessment:
- sleep is available
- the correct transport is the secondary Big Data service

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
- the currently tested realtime path did not produce usable values
- direct timestamped `0x14` historical probes produced no responses during the 2026-05-27 live test
- `0x69` data requests for blood pressure only acknowledged with zero-valued `0x69` responses

Assessment:
- blood pressure support is still unresolved
- a different historical path likely exists, but it is not proven yet

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

## Next Implementation Steps

1. Update `read_pressure_history_packet()` and `read_hrv_history_packet()` so the first request byte is a selector parameter instead of a hard-coded `0`.
2. Iterate selectors during backfill and incremental sync until the device returns `0xFF` no-data.
3. Keep the secondary Big Data transport for sleep and blood oxygen.
4. Refine the HRV decoder to 16-bit sample parsing and trim trailing empty slots correctly.
5. Investigate historical blood pressure separately.
