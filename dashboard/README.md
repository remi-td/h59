# H59 Dashboard

This directory now contains the primary visualization stack for `h59-local`.

The design follows the separation defined in
[Visualization Layer Architecture](../docs/software/visualisation_layer_architecture.md):

- `h59` CLI handles BLE, protocol, sync, and SQLite storage
- the dashboard reads the SQLite database through a small local API
- the browser UI is a mobile-first React app

## Layout

```text
dashboard/
  api/   FastAPI local API over h59.sqlite
  web/   React/Vite front-end
```

## Local Development

Use the runner script if you want simple start/stop/status handling:

```bash
cd dashboard
./run.sh start
./run.sh status
./run.sh logs api
./run.sh stop
```

To run the dashboard against the same database used by the CLI:

```bash
cd dashboard
./run.sh start --db "$(h59 db path)"
```

The runner manages the backend virtual environment for you under:

```text
dashboard/api/.venv/
```

On `start`, it will:
- create the API virtualenv if it does not exist
- sync/update Python dependencies from `dashboard/api/pyproject.toml`
- install/update frontend dependencies if `package.json` or `package-lock.json` changed
- start the API in stable non-reload mode by default, which is better suited to a background service
- use the `--db` override as `H59_DB_PATH` for the API if provided

This starts:
- API on `http://127.0.0.1:8000`
- web app on `http://127.0.0.1:5173`

Dashboard themes are configured separately from application logic:

```text
dashboard/web/src/theme-config.ts
dashboard/web/src/themes.css
```

Change `DEFAULT_DASHBOARD_THEME` in `theme-config.ts` to switch the default theme.

Runtime files go under:

```text
dashboard/.run/
```

You can override local runner ports with:

```text
H59_API_DEV_PORT
H59_WEB_DEV_PORT
H59_DASHBOARD_API_PYTHON
H59_DASHBOARD_API_RELOAD
```

`H59_DASHBOARD_API_PYTHON` is only needed if you want to force a specific Python for
bootstrapping the backend environment. In normal use, `./run.sh` will manage
`dashboard/api/.venv` itself.

Set `H59_DASHBOARD_API_RELOAD=1` only if you explicitly want `uvicorn --reload`.
For active API development, the manual foreground command is still the simplest option:

If you prefer manual processes:

Run the API:

```bash
cd dashboard/api
PYTHONPATH=src:../../src python -m uvicorn h59_dashboard_api.main:app --host 127.0.0.1 --port 8000 --reload
```

Run the web app:

```bash
cd dashboard/web
npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

The Vite dev server proxies `/api` to `http://127.0.0.1:8000` by default.

## Health Insights page

The default route, `http://localhost:5173/`, is the Health Insights page. It is intended as a first-stop summary for the selected device before drilling into the historical pages.

The page calls:

```text
GET /api/insights/current?device=preferred
```

The endpoint reads the same local SQLite database as the rest of the dashboard and returns:

- `sync_context`: latest band sync, sync age, feature-data age, data freshness, and stale-data warning text
- `confidence`: `low`, `medium`, or `high`, downgraded when sync data or feature data is stale, partial, empty, or uncertain
- `state`: an explainable current-state label such as `stable`, `sleep_deprived`, `under_recovered`, `physiological_strain`, `high_strain`, or `measurement_uncertain`
- `readiness`, `sleep`, and `strain` score objects
- `key_factors`: the local metrics and baseline deltas that explain the score
- `safety_flags` and `llm_guardrails`: reminders that wearable data is not diagnostic and abnormal BP/SpO2 observations require confirmation

The scoring layer is deterministic Python application logic in `dashboard/api/src/h59_dashboard_api/insights.py`. Reusable features and rolling baselines stay in SQLite views created by `src/h59_client/analytics.py`:

- `health_daily_features`
- `health_metric_observations`
- `health_metric_baselines`

This split keeps ingestion simple: the sync daemon does not need to refresh materialized insight tables. The API ensures the analytic views exist before serving the endpoint.

## Local Production with Docker

```bash
cd dashboard
cp .env.example .env
docker compose up -d
```

Open:

```text
http://localhost:8080
```

The API serves on:

```text
http://localhost:8000
```

## Runtime Model

The dashboard stack reads the same SQLite database produced by the CLI:

```text
../data/h59.sqlite
```

or whatever `H59_DB_PATH` points to in `.env`.

The API does not mutate measurement rows. If analytic views are missing after an upgrade, the API may create or refresh those SQLite views so read-only dashboard endpoints can query the current schema.

## First Implemented Endpoints

- `GET /api/health`
- `GET /api/devices`
- `GET /api/insights/current`
- `GET /api/today`
- `GET /api/metrics/{metric}`
- `GET /api/sleep`
- `GET /api/device/status`
- `GET /api/data-quality`
- `GET /api/debug`

## First Implemented Pages

- `Insights`
- `Today`
- `Trends`
- `Sleep`
- `Heart`
- `Oxygen`
- `Activity`
- `Device`
- `Debug`

## Notes

- The dashboard defaults to the preferred device.
- The device selector accepts `preferred`, `device_id`, nickname, address, or device name.
- All timestamps remain UTC at rest; the UI renders browser-local display time and explicitly labels the policy in the header.
