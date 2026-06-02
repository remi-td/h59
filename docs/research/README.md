# Research Notes

This section contains reverse-engineering results for the H59 device itself.

It is intentionally separate from the CLI software documentation.

Current research documents:
- [Device Protocol Map](device_protocol.md)
- [Historical Health Metrics Investigation](health_metrics.md)
- [Compatibility Mapping](compatibility_mapping.md)

The goal of these notes is to explain:
- which transports and commands are in use
- what data is actually available on the bracelet
- which decoders are proven, provisional, or still missing

Latest notable update:
- 2026-06-02 local-clock reconciliation against vendor-app screenshots is now documented
- stress / pressure-like history, HRV history, and the local-clock SpO2 hourly tail were reconciled to raw packet families
- heart-rate history remains partially unresolved because its current-day path still mixes UTC assumptions with bracelet-local clock behavior
