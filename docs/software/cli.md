# CLI Guide

## Purpose

`h59-local` is a Unix-style CLI for collecting and analyzing H59 smart band data locally.

The command surface is designed for:
- direct local use from a source checkout
- installation with `uv`
- unattended incremental sync as a background process

## Installation

Development install:

```bash
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

## Command Model

```bash
h59 <command> [options]
```

Commands:
- `sync`
- `report`
- `device`
- `daemon`
- `vibrate`
- `db`
- `config`

## Most Common Commands

One-shot sync:

```bash
h59 sync
```

Specific device sync:

```bash
h59 sync 1
h59 sync left-wrist
h59 sync 86B9D8D4-6CB2-E24D-815D-A141786F427B
```

Incremental sync:

```bash
h59 sync -i
```

Detached periodic incremental sync:

```bash
h59 sync -di --period 5m
```

Generate a markdown report:

```bash
h59 report
h59 report left-wrist
h59 report left-wrist --date 2026-05-27 --output report.md
```

Discover and register devices:

```bash
h59 device discover
h59 device list
h59 device nickname set 1 left-wrist
```

Inspect a device:

```bash
h59 device info left-wrist
h59 device capabilities left-wrist
```

Trigger vibration:

```bash
h59 vibrate
h59 device vibrate --repeat 2 --interval 1
```

Daemon lifecycle:

```bash
h59 daemon status
h59 daemon stop
```

Safe database reset:

```bash
h59 db reset
```

Print the effective database path:

```bash
h59 db path
```

## `report`

Purpose:
- render a markdown summary report for one device from the local SQLite database
- surface key metrics and validate data completeness against the stored history

Behavior:
- `h59 report` uses the preferred known device from the local database
- `h59 report <selector>` targets one registered device by `device_id`, `nickname`, or stored `address`
- the selected day defaults to the latest day found in the database for that device

Common flags:
- `--db <path>`
- `[selector]`
- `--date <YYYY-MM-DD>`
- `--output <path>`

## `sync`

Purpose:
- perform a one-shot sync
- or start a detached periodic sync worker

Behavior:
- `h59 sync` scans for all currently available H59 devices and syncs each of them
- `h59 sync <selector>` targets one device directly by `device_id`, `nickname`, or `address`
- known devices skip fresh discovery and connect directly by stored address
- `h59 sync -i` resumes from the latest recorded sync day for known devices
- if a device has no prior sync history, `h59 sync -i` performs an initial backfill and probes backward until the device stops returning daily history, within a bounded search window
- routine sync sets the bracelet clock as part of the capability handshake

Common flags:
- `-i`, `--incremental`
- `-d`, `--daemonize`
- `--period <duration>`
- `--db <path>`
- `[selector]`
- `--scan-timeout <seconds>`
- `--device-clock <utc|local>`
- `--config <path>`
- `--capture-gatt`
- `--realtime <metric>...`
- `--realtime-samples <n>`

Clock mode policy:
- default bracelet clock mode is `utc`
- `--device-clock local` switches a single command to local wall time
- `h59 config set-device-clock local` persists the default in the CLI config file
- `h59 config show` prints the effective configuration

Duration format:
- integer seconds, for example `300`
- `30s`
- `5m`
- `1h`

Default database path:
- source checkout: `./data/h59.sqlite`
- installed CLI with `XDG_DATA_HOME`: `$XDG_DATA_HOME/h59/h59.sqlite`
- installed CLI fallback: `~/.local/share/h59/h59.sqlite`

## `device`

Purpose:
- discover/register bracelets
- inspect a specific bracelet
- run one-shot device actions

Subcommands:
- `discover`
- `list`
- `nickname set`
- `info`
- `capabilities`
- `vibrate`
- `reboot`

Examples:

```bash
h59 device discover
h59 device list
h59 device nickname set 1 left-wrist
h59 device info left-wrist
h59 device capabilities left-wrist
h59 device vibrate left-wrist
h59 device reboot left-wrist
```

Note:
- `h59 device capabilities` performs the protocol set-time exchange using the configured bracelet clock mode

## `config`

Purpose:
- inspect and modify CLI configuration

Subcommands:
- `show`
- `set-device-clock`

Examples:

```bash
h59 config show
h59 config set-device-clock utc
h59 config set-device-clock local
```

## `daemon`

Purpose:
- manage the detached sync loop

Subcommands:
- `status`
- `stop`

Default state paths:
- state dir: `~/.local/state/h59`
- PID file: `~/.local/state/h59/daemon.pid`
- log file: `~/.local/state/h59/daemon.log`

## `db`

Purpose:
- manage the local SQLite database lifecycle

Subcommands:
- `reset`
- `path`

Behavior of `h59 db reset`:
- if the database exists, it is renamed to `archive_<YYYYMMDD-HHMISS>_h59.sqlite`
- a fresh database is then created at the configured `--db` path
- the archived file is retained and must be deleted manually if no longer needed

Behavior of `h59 db path`:
- prints the effective SQLite database path after resolving the default or the provided `--db`

## Exit Behavior

Expected exit codes:
- `0` success
- `1` operational failure
- `2` argument or usage error

Operational failures include:
- device not discoverable
- BLE connection failure
- daemon already running
- database write failure
