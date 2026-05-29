# h59-local

:warning: This project is in research stage and should be considered unstable. Bugs are guaranteed and contributions are welcome! :warning:

`h59-local` is a CLI for locally collecting and analyzing data from the H59 smart band.

The goal is simple:
- sync data directly over Bluetooth Low Energy (BLE)
- keep storage and analytics local, avoiding vendor saas dependencies
- enable private analytics on inexpensive wearable hardware with open algorithms

Repository:
- `https://github.com/remi-td/h59`

## What It Does

The current CLI can:
- discover and register nearby H59 devices
- run one-shot or incremental syncs into SQLite
- run as a detached periodic sync daemon
- store decoded measurements and raw protocol packets
- trigger simple device actions such as vibration and reboot
- prepare data for analytics
- generate markdown reports for a device and validate data completeness

An optional local serving application is also provided under `dashboard/`. It provides:
- a REST API serving the analytic data
- a local React dashboard for browsing trends and quality information

## Install

### Recommended: install with `uv`

```bash
uv tool install git+https://github.com/remi-td/h59.git
```

Upgrade an existing install:

```bash
uv tool install --force git+https://github.com/remi-td/h59.git
```

### From source
```bash
git clone https://github.com/remi-td/h59.git
cd h59
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

## Quickstart

Discover devices, run an initial sync:

```bash
# Discover devices and populate database
h59 device discover
h59 device nickname set 1 wristband # You can set a nickname (eg. "wristband") to your device (eg. device_id=1)
h59 sync -i                         # Incremental sync: if database is empty gathers all available history
h59 report 1 --output report.md     # Generate a report to inspect the collected data
```

Start the daemon service to sync every 15 minutes:
```bash
h59 sync -di --period 15m
h59 daemon status
```

You can list, inspect and identify (vibrate) discovered devices using their nickname (eg. "wristband"), device_id or address
```bash
h59 device list
h59 device info 1               
h59 vibrate 1 
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
- `h59 sync <device_id|nickname|address>`
- `h59 sync -i`
- `h59 sync -di --period 5m`
- `h59 report [device_id|nickname|address]`
- `h59 db reset`
- `h59 daemon status`
- `h59 daemon stop`
- `h59 device discover`
- `h59 device list`
- `h59 device nickname set <selector> <nickname>`
- `h59 device info [device_id|nickname|address]`
- `h59 device capabilities [device_id|nickname|address]`
- `h59 device vibrate [device_id|nickname|address]`
- `h59 device reboot [device_id|nickname|address]`
- `h59 vibrate [device_id|nickname|address]`

The top-level `h59 vibrate` command is kept as a shorthand for `h59 device vibrate`.

Selector behavior:
- `h59 sync` syncs all currently available H59 devices
- `h59 sync <selector>` targets one registered device by `device_id`, `nickname`, or stored address
- device action commands without a selector use the preferred known device from the local database
- `h59 report` without a selector uses the preferred known device from the local database

Incremental sync behavior:
- if a device already has sync history in the database, `h59 sync -i` resumes from the latest recorded sync day
- if the device has no prior sync history, `h59 sync -i` performs an initial backfill and probes backward until the device stops returning daily history, within a bounded search window

## Dashboard services

This project provides a REST API and dashboard services to easily access the analytical data. These services are not installed through the CLI package. 
They live under `dashboard/` and is run from the source checkout.

Clone the repo first, then use the runner:

```bash
git clone https://github.com/remi-td/h59.git
cd h59/dashboard
./run.sh start
```

Open:

```text
http://127.0.0.1:5173
```

The runner will:
- create and update `dashboard/api/.venv`
- install frontend dependencies under `dashboard/web/`
- start the API on `http://127.0.0.1:8000`
- start the web app on `http://127.0.0.1:5173`

Useful service commands:

```bash
cd dashboard
./run.sh status
./run.sh logs api
./run.sh logs web
./run.sh restart
./run.sh stop
```

## Approach

The software follows a local-first pipeline:

1. Discover and register devices when needed.
2. Connect directly to known devices by stored address for fast interactions.
3. Query supported protocol surfaces.
4. Store decoded history plus raw evidence in SQLite.
5. Build analysis and reporting on top of the local database.

## Safe Database Reset

To start with a fresh schema without deleting the old file:

```bash
h59 db reset
```

Behavior:
- if the database exists, it is renamed to `archive_<YYYYMMDD-HHMISS>_h59.sqlite`
- a new empty database is then created with the current schema
- the archived database is kept on disk and must be deleted manually if no longer needed

Research notes are kept separately so the CLI software stays clean while the reverse-engineering work remains documented.

## Documentation

Software documentation:
- [CLI Guide](/Users/remi.turpaud/Code/h59/docs/software/cli.md:1)
- [Software Architecture](/Users/remi.turpaud/Code/h59/docs/software/architecture.md:1)
- [Architecture TODO](/Users/remi.turpaud/Code/h59/docs/software/architecture_todo.md:1)
- [Database Design](/Users/remi.turpaud/Code/h59/docs/software/database.md:1)
- [Dashboard Requirements](/Users/remi.turpaud/Code/h59/docs/software/dashboard_requirements.md:1)

Device research:
- [Research Overview](/Users/remi.turpaud/Code/h59/docs/research/README.md:1)
- [Device Protocol Map](/Users/remi.turpaud/Code/h59/docs/research/device_protocol.md:1)
- [Historical Health Metrics Investigation](/Users/remi.turpaud/Code/h59/docs/research/health_metrics.md:1)
- [Compatibility Mapping](/Users/remi.turpaud/Code/h59/docs/research/compatibility_mapping.md:1)

Visualization:
- [Dashboard README](/Users/remi.turpaud/Code/h59/dashboard/README.md:1)
- [Visualization Layer Architecture](/Users/remi.turpaud/Code/h59/docs/software/visualisation_layer_architecture.md:1)

Contributor guidance:
- [AGENT.md](/Users/remi.turpaud/Code/h59/AGENT.md:1)

## Repository Layout

- `src/h59_client/`: installable CLI package
- `tests/`: unit tests
- `tools/`: small project utilities
- `dashboard/`: optional FastAPI + React local web dashboard
- `docs/software/`: user-facing software documentation
- `docs/research/`: reverse-engineering findings kept separate from CLI docs
- `data/`: runtime databases and generated outputs, intentionally not tracked

## Development

Run tests with:

```bash
uv run pytest
```

Run the dashboard manually without the runner:

```bash
cd dashboard/api
PYTHONPATH=src:../../src python -m uvicorn h59_dashboard_api.main:app --host 127.0.0.1 --port 8000 --reload
```

```bash
cd dashboard/web
npm install
npm run dev
```
