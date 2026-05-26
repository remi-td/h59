# h59-local

`h59-local` is a CLI for locally collecting and analyzing data from the H59 smart band.

The goal is simple:
- sync data directly over BLE
- keep storage and analytics local
- avoid vendor cloud dependencies
- enable privacy-first analytics on inexpensive wearable hardware

Repository:
- `https://github.com/remi-td/h59`

## What It Does

The current CLI can:
- discover and inspect nearby H59 devices
- run one-shot or incremental syncs into SQLite
- run as a detached periodic sync daemon
- store decoded measurements and raw protocol packets
- trigger simple device actions such as vibration and reboot

## Install

### Recommended: install with `uv`

```bash
uv tool install git+https://github.com/remi-td/h59.git
```

Upgrade an existing install:

```bash
uv tool install --force git+https://github.com/remi-td/h59.git
```

### One-line installer

```bash
curl -LsSf https://raw.githubusercontent.com/remi-td/h59/main/install.sh | sh
```

If `uv` is not already installed, the script bootstraps it first.

## Quickstart

Copy and paste:

```bash
git clone https://github.com/remi-td/h59.git
cd h59
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"

h59 device info --name H59
h59 sync
h59 sync -i
h59 sync -di --period 5m
h59 daemon status
```

## Default Database Location

- from the source checkout: `./data/h59.sqlite`
- from an installed CLI: `$XDG_DATA_HOME/h59/h59.sqlite`
- fallback installed path: `~/.local/share/h59/h59.sqlite`

## CLI

Primary command:

```bash
h59 <command> [options]
```

Main commands:
- `h59 sync`
- `h59 sync -i`
- `h59 sync -di --period 5m`
- `h59 daemon status`
- `h59 daemon stop`
- `h59 device info`
- `h59 device capabilities`
- `h59 device vibrate`
- `h59 device reboot`
- `h59 vibrate`

The top-level `h59 vibrate` command is kept as a shorthand for `h59 device vibrate`.

## Approach

The software follows a local-first pipeline:

1. Connect to the bracelet over BLE.
2. Query supported protocol surfaces.
3. Store decoded history plus raw evidence in SQLite.
4. Build analysis and reporting on top of the local database.

Research notes are kept separately so the CLI software stays clean while the reverse-engineering work remains documented.

## Documentation

Software documentation:
- [CLI Guide](/Users/remi.turpaud/Code/h59/docs/software/cli.md:1)
- [Database Design](/Users/remi.turpaud/Code/h59/docs/software/database.md:1)
- [Dashboard Requirements](/Users/remi.turpaud/Code/h59/docs/software/dashboard_requirements.md:1)

Device research:
- [Research Overview](/Users/remi.turpaud/Code/h59/docs/research/README.md:1)
- [Device Protocol Map](/Users/remi.turpaud/Code/h59/docs/research/device_protocol.md:1)
- [Historical Health Metrics Investigation](/Users/remi.turpaud/Code/h59/docs/research/health_metrics.md:1)
- [Compatibility Mapping](/Users/remi.turpaud/Code/h59/docs/research/compatibility_mapping.md:1)

Contributor guidance:
- [AGENT.md](/Users/remi.turpaud/Code/h59/AGENT.md:1)

## Repository Layout

- `src/h59_client/`: installable CLI package
- `tests/`: unit tests
- `tools/`: small project utilities
- `docs/software/`: user-facing software documentation
- `docs/research/`: reverse-engineering findings kept separate from CLI docs
- `data/`: runtime databases and generated outputs, intentionally not tracked

## Development

Run tests with:

```bash
uv run pytest
```
