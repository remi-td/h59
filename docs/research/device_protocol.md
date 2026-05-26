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
- proven available
- decoder still provisional

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
- final sleep field semantics
- final blood oxygen field semantics
- exact meaning of some pressure/stress-like values
