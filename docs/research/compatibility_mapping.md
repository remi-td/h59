# Compatibility Mapping

This is the only place in the tracked documentation that keeps the historical mapping to the external `colmi_r02_client` project.

Reference repository:
- https://github.com/tahnok/colmi_r02_client

## Why This Mapping Exists

Earlier reverse-engineering work validated that the H59 shares part of its legacy UART protocol surface with that external client.

That mapping was useful for:
- packet framing
- battery retrieval
- heart-rate history
- activity history
- capability probing

The current CLI no longer depends on that package.

## Schema and Feature Mapping

| Local project concept | External client concept | Notes |
|---|---|---|
| `devices` | `rings` | Local project uses a generic device model |
| `syncs` | `syncs` | Same role |
| `heart_rates` | `heart_rates` | Same role |
| `sport_details` | `sport_details` | Same role |
| `battery_samples` | battery query | Added as a first-class table locally |
| `heart_rate_settings` | heart-rate settings query | Added as a first-class table locally |
| `capability_snapshots` | set-time capability response | Added as a first-class table locally |
| `realtime_samples` | realtime measurement requests | Added as a first-class table locally |
| `raw_packets` | packet recording | Local persistence table for future decoders |
| `sleep_sessions` | no equivalent | Local extension for H59-specific decoding |

## Protocol Surface Mapping

| Local decoder / transport | External mapping |
|---|---|
| UART battery | compatible |
| UART heart-rate history | compatible |
| UART activity history | compatible |
| UART heart-rate settings | compatible |
| UART capability snapshot | compatible |
| Big Data sleep | no equivalent in that client |
| Big Data blood oxygen | no equivalent in that client |
| UART pressure history | no equivalent in that client |
| UART HRV history | no equivalent in that client |

## Conclusion

The external client was a useful starting point for the legacy UART subset.

It is not sufficient for full H59 historical coverage, especially for:
- sleep
- blood oxygen
- pressure/stress-like history
- HRV history

It is also not sufficient for the bracelet-clock reconciliation work proved on 2026-06-02:
- local-clock `0x37` pressure/stress slots need bracelet-local half-hour anchoring
- local-clock `0x39` HRV slots need bracelet-local hourly anchoring
- local-clock Big Data `0x2a` exposes an hourly SpO2 tail with no equivalent in the external client
- heart-rate current-day behavior still needs H59-specific investigation because the remaining issue is now about day-boundary semantics, not generic packet framing
