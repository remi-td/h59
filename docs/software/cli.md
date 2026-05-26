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
- `device`
- `daemon`
- `vibrate`

## Most Common Commands

One-shot sync:

```bash
h59 sync
```

Incremental sync:

```bash
h59 sync -i
```

Detached periodic incremental sync:

```bash
h59 sync -di --period 5m
```

Inspect the device:

```bash
h59 device info --name H59_DEMO
h59 device capabilities --name H59_DEMO
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

## `sync`

Purpose:
- perform a one-shot sync
- or start a detached periodic sync worker

Common flags:
- `-i`, `--incremental`
- `-d`, `--daemonize`
- `--period <duration>`
- `--db <path>`
- `--name <device-name>`
- `--scan-timeout <seconds>`
- `--skip-capabilities`
- `--realtime <metric>...`
- `--realtime-samples <n>`

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
- inspect the bracelet
- run one-shot device actions

Subcommands:
- `info`
- `capabilities`
- `vibrate`
- `reboot`

Examples:

```bash
h59 device info
h59 device capabilities
h59 device vibrate
h59 device reboot
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
