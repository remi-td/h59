# Historical Health Metrics Investigation

Date:
- 2026-05-26

## Goal

Determine whether the H59 actually exposes historical sleep and health metrics, or whether the current sync was simply not querying the correct protocol surfaces.

## Summary

The current sync was incomplete.

What is now proven:
- sleep history is available
- historical blood oxygen is available
- historical pressure/stress-like data is available
- historical HRV data is available

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

Assessment:
- historical pressure/stress-like data is available

### HRV History

Result:
- UART command `0x39` returned a valid historical split response
- the payload looks like a 16-bit series rather than single-byte samples

Assessment:
- historical HRV is available
- the decoder still needs refinement

### Blood Pressure

Result:
- capability flags and settings indicate support
- the currently tested realtime path did not produce usable values

Assessment:
- blood pressure support is still unresolved
- a different historical path likely exists, but it is not proven yet

## Practical Conclusion

The missing metrics were not mainly a “not enough history” problem.

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

## Next Implementation Steps

1. Add the secondary Big Data transport to `h59_client`.
2. Persist raw Big Data payloads into SQLite.
3. Add first-class decoded tables for sleep, blood oxygen, pressure, and HRV.
4. Refine the HRV decoder to 16-bit sample parsing.
5. Investigate historical blood pressure separately.
