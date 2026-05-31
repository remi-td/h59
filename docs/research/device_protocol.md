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

### HRV history

Transport:
- primary UART-like service

Command:
- `0x39`

Assessment:
- proven available
- sample decoding needs refinement to 16-bit values

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
