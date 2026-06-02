# Device Protocol Map

## Device Identity

Observed example values:
- advertised local name: `H59_DEMO`
- BLE address on macOS: `2F1A9C7E-4D82-4A6F-9C11-7B8D2A1E5C44`
- hardware version: `H59_V2.2`
- firmware version: `H59_2.20.02_260319`

These example identifiers are placeholders. Real device addresses are intentionally omitted from the tracked documentation.

## GATT Services

### Primary UART-like service

Service:
- `6e40fff0-b5a3-f393-e0a9-e50e24dcca9e`

Characteristics:
- `6e400002-b5a3-f393-e0a9-e50e24dcca9e`
  - write path for 16-byte protocol commands
- `6e400003-b5a3-f393-e0a9-e50e24dcca9e`
  - notify path for 16-byte protocol responses

This is the primary transport used by the CLI today.

### Secondary Big Data service

Service:
- `de5bf728-d711-4e47-af26-65e3012a5dc7`

Characteristics:
- `de5bf72a-d711-4e47-af26-65e3012a5dc7`
  - write path
- `de5bf729-d711-4e47-af26-65e3012a5dc7`
  - notify path

This transport is required for full historical coverage of some health metrics.

### Device Information service

Service:
- `0000180a-0000-1000-8000-00805f9b34fb`

Useful characteristics:
- `00002a27-0000-1000-8000-00805f9b34fb` — hardware version
- `00002a26-0000-1000-8000-00805f9b34fb` — firmware version

### `fee7` vendor service

Observed characteristics:
- `0000fea1-0000-1000-8000-00805f9b34fb`
- `0000fea2-0000-1000-8000-00805f9b34fb`
- `0000fec9-0000-1000-8000-00805f9b34fb`

Assessment:
- present on the device
- not required for the currently proven history paths
- still worth keeping in mind for future research

## Proven Historical Data Paths

### Heart-rate history

Transport:
- primary UART-like service

Command:
- `0x15`

Observed shape:
- 288 possible samples per day
- 5-minute sample interval

Assessment:
- proven
- stable decoder implemented

### Activity history

Transport:
- primary UART-like service

Command:
- `0x43`

Observed shape:
- 15-minute bins
- steps
- distance
- calories-like field

Assessment:
- proven
- stable decoder implemented

### Sleep history

Transport:
- secondary Big Data service

Assessment:
- sleep payload proven available
- decoder still provisional
- multi-night backfill from one sync is not proven
- current sync asks for sleep only once per run, unlike heart-rate and activity backfill

### Blood oxygen history

Transport:
- secondary Big Data service

Assessment:
- proven available
- decoder still provisional

### Pressure / stress-like history

Transport:
- primary UART-like service

Command:
- `0x37`

Assessment:
- proven available
- semantics still need dashboard-level interpretation
- selector `0` is a partial current-day buffer, not a guaranteed full current day
- on 2026-05-31 the current-day buffer stopped advancing at `17:00 UTC` and the bracelet returned explicit zeroes for later slots

### HRV history

Transport:
- primary UART-like service

Command:
- `0x39`

Assessment:
- proven available
- sample decoding needs refinement to 16-bit values
- selector `0` is also a partial current-day buffer
- the current proven split layout only has room for about `25` 16-bit samples, which is about `12.5` hours at a `30` minute interval
- that capacity ceiling matches the observed half-day-ish HRV coverage in the database

## Observed Retention

Live backfill behavior on 2026-05-28:
- a fresh initial backfill successfully queried a 7-day window
- the device returned stored history back to `2026-05-24`
- `2026-05-24` matches the start of actual use for the tested bracelet

Assessment:
- this is consistent with roughly 7 days of on-device history retention
- the exact retention ceiling is still inferred rather than directly proven
- fresh pulls reproduced the same missing intervals, so those gaps were present in the device's accessible history at sync time

## Capability Flags

The set-time response advertises support for:
- blood oxygen
- blood pressure
- one-key check
- new sleep protocol
- pressure
- HRV

Assessment:
- capability flags are useful hints
- they are not enough on their own; each path still needs live validation

## Current Gaps

Still unresolved:
- historical blood pressure extraction
- whether any path other than `HealthCheck` can backfill blood-pressure history
- final sleep field semantics
- whether the proven Big Data sleep request can backfill several older nights or only the latest night
- final blood oxygen field semantics
- exact meaning of some pressure/stress-like values

Proven on 2026-05-30:
- realtime `0x69 / dataType=5` (`HealthCheck`) emits final BP readings
- realtime `0x69 / dataType=2` does not emit final systolic/diastolic values on this bracelet
- normal historical `sync` traffic does not currently expose any additional paired-BP command beyond the known history set (`1`, `3`, `21`, `22`, `39`, `42`, `47`, `55`, `57`, `67`)
- the only unmapped historical reply seen in captured sync traffic is a fixed `0x2f` packet, not a timestamped measurement series

Proven on 2026-05-31:
- `Settings ID 12` decodes as an hourly blood-pressure auto-measure configuration:
  - enabled = `1`
  - time range = `00:00 -> 23:00`
  - multiple = `60`
- this strongly suggests the bracelet exposes at least some writable scheduling/configuration surface for automatic measurement, worth exploring later as a separate device-configuration feature
- by shape alone, `Settings ID 22` (heart rate) also looks interval-configurable, while `44`, `54`, and `56` currently look more like enable/disable toggles than interval settings
- periodic measurement on/off control is now proven for:
  - `12` blood pressure
  - `44` SpO2
  - `54` stress / pressure-like detection
  - `56` HRV
- read shape:
  - request payload `[1]`
  - reply byte `2` behaves as the enabled flag
- live read examples:
  - `0c0101000017003c0000000000000061` -> blood pressure enabled
  - `2c01010000000000000000000000002e` -> SpO2 enabled
  - `36010000000000000000000000000037` -> stress disabled
  - `3801010000000000000000000000003a` -> HRV enabled
- write shape:
  - request payload `[2, 1]` enables the periodic measurement
  - request payload `[2, 0]` disables it
- live round-trip write was proven for `stress`:
  - `h59 device set stress on ...`
  - follow-up read confirmed `enabled = 1`
- direct `cmd 20` probes still returned nothing, even when timestamps were encoded using local-wall-clock semantics
- a clean retry of `cmd 13` with explicit settling and direct-address reconnect showed only explicit no-data (`0dff...`) for:
  - empty payload
  - simple subtypes `0`, `1`, `2`
  - interval-like payloads (`30`, `60`)
  - decimal and BCD day/date payloads for today, yesterday, two days ago, and five days ago
- the earlier apparent two-packet `cmd 13` result was most likely polluted by overlapping async traffic from other commands in the same probe session
- `cmd 14` did not unlock any additional BP-history packets
- a UART neighborhood sweep around the known historical-series commands found:
  - `50`..`53` returning explicit `0xee` no-data
  - `58` producing no response
  - `59` echoing the request payload only
  - `60` returning the same fixed packet for every tested payload:
    - `3c00400020000000000000000000009c`
  - `61`, `63`, `64`, `65`, and `66` returning explicit `0xee` no-data
- a broader payload-shape probe on `cmd 60` showed the same fixed response for:
  - one-byte selectors
  - two-byte index-like payloads
  - decimal and BCD date payloads
  - interval-tagged variants
- a wider undocumented Big Data scan found:
  - a few short non-empty payloads at `44`, `67 -> 68`, and `90`
  - a uniform one-byte body `40` for every tested id `91..140`
- none of those Big Data responses looked like an hourly paired systolic/diastolic history stream

Proven on 2026-06-02 against app screenshots taken around `21:01` local time (`Europe/Paris`), with the bracelet and vendor app both switched to local clock mode:
- the vendor app should be treated as the source of truth for local-clock reconciliation of currently visible historical rows
- a clean sync with `--device-clock local` reproduced three distinct packet families:
  - `0x37` pressure/stress history
  - `0x39` HRV history
  - Big Data `0x2a` blood oxygen history

Pressure / stress-like reconciliation:
- the app's visible stress rows matched the `0x37` values exactly
- matching rule:
  - `sample_index` is a local half-hour-of-day slot
  - zero-valued slots are omitted by the app
- example visible app rows:
  - `21:00 -> 32`
  - `18:30 -> 44`
  - `18:00 -> 46`
  - `17:30 -> 35`
- matching raw decoded rows from the same sync carried those exact values at indexes:
  - `42 -> 32`
  - `37 -> 44`
  - `36 -> 46`
  - `35 -> 35`
- implication:
  - our current storage anchoring for `pressure_samples` is off by the local UTC offset when the bracelet clock is in local mode

HRV reconciliation:
- the app's visible HRV rows matched the decoded `0x39` values, but not the current stored timestamps
- matching rule:
  - `sample_index` behaves like a local hour-of-day slot
  - zero-valued slots are omitted by the app
  - the current parser's `range_minutes = 30` does not match the app-visible history cadence for this packet family
- example visible app rows:
  - `21:00 -> 38 ms`
  - `18:00 -> 44 ms`
  - `17:00 -> 35 ms`
  - `16:00 -> 38 ms`
- matching decoded value indexes from the same sync:
  - `21 -> 38`
  - `18 -> 44`
  - `17 -> 35`
  - `16 -> 38`
- indexes `19` and `20` decoded as zero in that same payload, which explains why the app jumped from `18:00` to `21:00`
- implication:
  - `0x39` is not just suffering from timezone anchoring; its visible app cadence is also being misinterpreted by the current decoder

Blood oxygen reconciliation:
- the local-clock Big Data `0x2a` payload changed shape compared with earlier UTC-clock captures
- captured local-clock example:
  - packet length `153` bytes
  - declared data length `147`
  - body flag byte `2`
- the current parser incorrectly treats the whole body as a flat 2-byte min/max stream
- in the local-clock payload, the tail region beginning at payload offset `112` contained duplicated hourly values:
  - `98, 98, 97, 96, 96, 97, 96, 96, 98, 97, 99, 98, 0, 0, 0, 0, 0`
- those values matched the app's visible hourly rows from `07:00-08:00` through `18:00-19:00` exactly:
  - `07:00-08:00 -> 98-98`
  - `08:00-09:00 -> 98-98`
  - `09:00-10:00 -> 97-97`
  - `10:00-11:00 -> 96-96`
  - `11:00-12:00 -> 96-96`
  - `12:00-13:00 -> 97-97`
  - `13:00-14:00 -> 96-96`
  - `14:00-15:00 -> 96-96`
  - `15:00-16:00 -> 98-98`
  - `16:00-17:00 -> 97-97`
  - `17:00-18:00 -> 99-99`
  - `18:00-19:00 -> 98-98`
- implication:
  - the local-clock `0x2a` payload contains an hourly summary tail the current parser ignores completely
  - the existing `BloodOxygenHistory.samples_with_times()` model is not valid for that payload shape

Historical blood pressure reconciliation:
- the vendor app screenshot showed hourly paired values such as:
  - `19:00 -> 122/82`
  - `18:00 -> 124/86`
  - `17:00 -> 127/86`
  - `16:00 -> 130/90`
  - `15:00 -> 128/89`
- the visible pattern repeated cyclically in the screenshot, which does not resemble the other captured historical series
- the clean local-clock sync still did not capture any historical paired-BP packet family beyond the already known settings and realtime paths
- implication:
  - the app's historical BP screen still does not map to a proven raw history packet in the local sync traffic
  - those rows should not currently be used to infer `0x37`, `0x39`, or Big Data `0x2a` semantics
