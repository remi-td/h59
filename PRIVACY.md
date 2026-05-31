# Privacy Notes

## Project Position

`h59-local` is designed to keep collection, storage, analytics, and visualization local.

The project aims to avoid:
- vendor cloud sync
- third-party health data processors
- unnecessary transmission of device data off the local machine

## Local Data Classes

The local environment may contain:
- BLE device identifiers such as addresses and advertised names
- raw packet captures
- timestamps of health and activity events
- derived health metrics such as heart rate, sleep, SpO2, HRV, stress-like values, and blood-pressure-like readings
- dashboard screenshots or generated reports

These may be personal data or health-adjacent data.

## Storage Policy

The core software stores timestamps in UTC in SQLite.

The repository itself should not contain runtime data.

Runtime and research artifacts should remain local and untracked:
- `data/`
- `misc/artifacts/`
- `captures/`
- `traces/`
- generated dashboard runtime directories

## Sharing Guidance

When showing the project to others:
- share the git repository, not the whole working tree
- avoid sharing local SQLite files
- avoid sharing raw packet captures unless they are intentionally scrubbed
- replace real device identifiers in examples with placeholders
- review screenshots for health values, timestamps, and local paths before publishing

## Reverse-Engineering Notes

Research documents may describe real protocol behavior and example payloads.

Those documents should:
- use generic example device names and selectors where possible
- avoid absolute personal filesystem paths
- avoid embedding local runtime dumps that contain personal data

## Dashboard and API Boundary

The dashboard and API are local-serving components by design.

They should remain stateless with respect to external services and should not add remote analytics, trackers, or telemetry without an explicit architecture decision and documentation update.
