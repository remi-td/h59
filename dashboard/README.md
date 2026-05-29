# H59 Dashboard

This directory contains the optional visualization layer for `h59-local`.

It is intentionally separate from the core CLI:
- the CLI collects, decodes, stores, and validates data
- Grafana reads the SQLite database in read-only mode

## What Is Here

- `docker-compose.yml`
  - local Grafana runtime
- `provisioning/`
  - reproducible datasource and dashboard provisioning
- `dashboards/`
  - provisioned Grafana dashboard JSON
- `sql/`
  - optional helper SQL and example queries
- `Makefile`
  - convenience commands

## Prerequisites

- Docker and Docker Compose
- an existing H59 SQLite database

Create the database first if needed:

```bash
h59 sync -i
```

By default, the dashboard expects the source-checkout database:

```text
../data/h59.sqlite
```

If your CLI was installed globally and uses an XDG data path instead, override `H59_DB_PATH` in `.env`.

## Quickstart

```bash
cd dashboard
cp .env.example .env
docker compose up -d
```

Open:

```text
http://localhost:3000
```

Default local login comes from `.env.example`:
- user: `admin`
- password: `admin`

Change it before exposing Grafana outside your laptop or LAN.

## Runtime Model

The Grafana container mounts the SQLite database read-only:

```text
${H59_DB_PATH} -> /h59-data/h59.sqlite:ro
```

Grafana never writes back into the H59 database.

## Dashboards

Provisioned dashboards:
- `H59 Overview`
- `H59 Sleep & Recovery`
- `H59 Data Quality`

They use a `device` variable populated from the `devices` table, so the same dashboard can target any registered bracelet in the database.

## SQL Layer

The dashboards query the base schema directly so they work without modifying the SQLite file.

Optional helper SQL lives in `sql/`:
- `views.sql`
- `dashboard_summary.sql`
- `example_queries.sql`

These are reference assets for ad hoc analysis or future materialized views.

## Operations

```bash
make up
make down
make logs
make restart
```

On macOS:

```bash
make open
```

## Notes

- The Grafana SQLite datasource plugin is installed automatically on first start.
- Dashboard timestamps are rendered from UTC data already stored by the CLI.
- The current MVP focuses on real local data availability and completeness, not vendor-style UI parity.
