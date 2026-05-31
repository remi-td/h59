# AGENT.md

## Purpose

This repository contains `h59-local`, a Unix-style CLI for privacy-first local collection and analysis of H59 smart band data.

The two product goals are:
- collect data directly from the device over BLE
- keep storage and analytics local, without vendor cloud dependencies

## Project Structure

- `src/h59_client/`: installable package and CLI implementation
- `tests/`: unit tests
- `docs/software/`: user-facing software documentation
- `docs/research/`: reverse-engineering and protocol findings
- `tools/`: small local utilities
- `data/`: runtime databases and generated outputs, intentionally untracked
- `misc/`: legacy probes, old notes, and generated artifacts, intentionally untracked

## Contribution Rules

1. Keep the CLI surface clean and Unix-like.
2. Keep software docs separate from reverse-engineering notes.
3. Do not reintroduce tracked runtime data, captures, or personal device identifiers.
4. Preserve UTC-only timestamp storage semantics.
5. Preserve raw protocol evidence when adding new decoders.
6. Keep `SECURITY.md` and `PRIVACY.md` aligned with repository practice.

## Timestamp Policy

SQLite has no native timezone-aware timestamp type in this project.

Use:
- UTC only
- ISO-8601 text
- explicit `+00:00` offsets

Do not store local timestamps in the database.
Timezone conversion belongs in reporting and dashboard layers.

## Device and Privacy Rules

- Replace real device identifiers in examples with generic placeholders.
- Do not commit data from `data/`, `captures/`, `traces/`, or `misc/`.
- Treat vendor-estimated health metrics as non-medical unless proven otherwise.
- Prefer sharing the git repository rather than the full working tree.
- Clean generated runtime/build directories before external review when practical.

Reference documents:
- `SECURITY.md`
- `PRIVACY.md`

## Development Workflow

Install dev dependencies:

```bash
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

Run tests:

```bash
uv run pytest
```

Run the CLI from source:

```bash
uv run h59 --help
uv run h59 sync -i
```

## Expected Engineering Pattern

When adding a new metric:

1. Capture and preserve raw packets.
2. Add a parser in `src/h59_client/protocol.py`.
3. Add first-class storage when the data is stable enough to query.
4. Keep provisional fields clearly marked when semantics are not fully trusted.
5. Add tests using real or representative captured payloads.
6. Update the relevant software and research docs.

## Current Known Boundaries

- Heart rate history is established.
- Activity history is established.
- Sleep, SpO2, HRV, and pressure/stress-like history are implemented, but some field semantics are still provisional.
- Historical blood pressure is still unresolved.
