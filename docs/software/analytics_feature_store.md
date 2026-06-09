# Analytics Feature Store Architecture

## Purpose

The analytics sprint moves H59 from one-off dashboard calculations to a reusable local feature store over the existing SQLite history.

The goal is not medical diagnosis. The feature store supports personal-trend wellness analytics with explicit provenance, confidence, and data-quality state.

## Design priorities

1. Extendibility: new metrics should be added by registering catalog metadata and exposing deterministic feature rows, not by wiring bespoke dashboard cards directly to raw tables.
2. Operational simplicity: analytics remain query-time SQLite views and Python functions unless measured latency requires materialized tables.
3. Robustness: existing databases may have stale view definitions, so bootstrap validates required columns with `PRAGMA table_info` and rebuilds the analytic surface when definitions drift.
4. Device isolation: BLE sync and the base CLI remain raw-capture focused. Analytics must replay from stored history without requiring the bracelet to be nearby.
5. Safety: every score and physiological indicator is a local wellness estimate with confidence and approximation labels.

## Layering

```text
Raw capture tables
  devices, syncs, heart_rates, sport_details, sleep_*, hrv_samples,
  pressure_samples, blood_oxygen_samples, blood_pressure_readings,
  realtime_samples, raw_packets
      ↓ deterministic SQL projections
Feature store
  metric catalog (Python metadata)
  health_feature_observations (normalized long-form view)
  health_daily_feature_store (wide day/device view)
  health_feature_baselines (rolling baseline/status view)
      ↓ Python scoring and relationship engines
Analytics APIs
  /api/metrics/catalog
  /api/features
  /api/features/daily
  /api/insights/current
  /api/sleep/summary
  /api/strain/daily
  /api/workouts
  /api/trends
  /api/compare
  /api/correlations
  /api/behavior-effects
      ↓ dashboard pages/cards
Explainable UI
```

## Raw capture contract

The device layer owns data acquisition and persistence. It must not be coupled to readiness, strain, correlation, behavior-effect, or dashboard scoring logic.

Analytics may only depend on tables already written by the storage layer. If a feature needs better raw evidence later, add capture fields without making the daemon compute feature rows during BLE sync.

## Feature observation contract

`health_feature_observations` is the normalized long-form feature surface. Every row includes:

- `device_id`
- `feature_name`
- `feature_value`
- `unit`
- `valid_from` / `valid_to`
- `feature_date`
- `source_kind`
- `source_table`
- `source_id`
- `data_quality_state`
- `confidence`
- `observation_as_of`
- `approximation_label`

This view is intended for API series, trends, correlations, and baseline calculations.

## Daily feature-store contract

`health_daily_feature_store` is the wide row shape used by scoring code and dashboards that need a compact daily snapshot. It is initially a view over `health_daily_features` plus derived columns. It must remain rebuildable from raw history.

Compatibility rule: keep `health_daily_features`, `health_metric_observations`, and `health_metric_baselines` available for existing consumers. Add versioned or richer views rather than breaking existing names.

## Baseline model

`health_feature_baselines` exposes rolling 7/14/30/60-day baseline rows per device/metric/date. Rows include mean, median, sample count, spread, latest observation timestamp, and a status:

- `calibrating`: fewer than the minimum useful observations
- `provisional`: enough observations for directional comparisons only
- `trusted`: enough observations and fresh data
- `stale`: latest underlying feature is too old

Python scoring code owns directional robust z-score normalization and winsorization so SQL remains deterministic and easy to inspect.

## Scoring and explanation model

Scoring belongs in Python application modules. SQL exposes reusable facts; Python composes those facts into:

- readiness scores and labels
- ranked positive and negative drivers
- omitted or low-confidence terms
- strain and workout estimates
- correlation and lag scans
- behavior-effect comparisons
- plain-English explanations

Every score must expose components and should degrade to `measurement_uncertain` rather than sounding precise when data is stale, sparse, or vendor-derived.

## Metric catalog

The catalog is code-owned metadata for all user-visible feature metrics. It provides stable keys, labels, units, category, directionality, source, minimum days, baseline support, dashboard defaults, and approximation level.

Adding a metric requires:

1. catalog entry
2. feature observation rows or daily-store field
3. tests for metadata/API behavior
4. dashboard copy that labels approximation and confidence

## Blood pressure and pressure safety

- Finished BP features may use `blood_pressure_readings` or realtime `health-check.systolic` / `health-check.diastolic` pairs only.
- Realtime cuff-pressure streams must never feed final systolic/diastolic BP metrics.
- `pressure_samples` must be described as a pressure/stress-like vendor score.
- Abnormal BP/SpO2 values should trigger conservative repeat-measurement wording, not diagnosis.

## Operational upgrade notes

This sprint is designed as an in-place upgrade for users already running H59.

### Database upgrade behavior

No destructive migration or manual backfill is required. The raw SQLite tables remain the source of truth, and the new analytics surfaces are deterministic views over existing history.

On dashboard/API startup, and before analytics payloads are served, `ensure_analytic_surface` validates the analytic views and rebuilds them when they are missing or stale. This covers both new installs and existing databases that still contain older `CREATE VIEW` definitions.

Expected new or refreshed views:

- `health_feature_observations`
- `health_daily_feature_store`
- `health_feature_baselines`
- compatibility views: `health_daily_features`, `health_metric_observations`, `health_metric_baselines`

A current user can therefore upgrade code, restart the dashboard API, and let the first analytics request rebuild the view layer. If needed, operators can verify the active database with:

```bash
h59 db path
sqlite3 "$(h59 db path)" ".tables"
```

The feature-store views are safe to drop and recreate because they do not own source data.

### Dashboard restart procedure

After deploying the new code, restart the dashboard services so the API and web bundle pick up the new endpoints and Explore page.

For the repository dashboard runner:

```bash
cd dashboard
./run.sh stop
./run.sh start --db "$(h59 db path)"
./run.sh status
curl -fsS http://127.0.0.1:8000/api/health
```

If the API was started with a database override, verify `/api/health` reports the expected active database path after restart.

### Scheduled work

No new scheduler, cron job, daemon flag, or materialized-table refresh task is required for this sprint. Existing device sync schedules can continue unchanged.

The new analytics are intentionally query-time/replay-time views plus Python payload builders. Add scheduled materialization only if production measurements show that view latency is a real problem.

### What's new after upgrade

Users and downstream tools gain:

- `/api/metrics/catalog` for stable metric metadata.
- `/api/features` and `/api/features/daily` for reusable feature-store rows.
- sleep, strain, workout, trend, compare, correlation, and behavior-effect API surfaces.
- expanded `/api/insights/current` readiness attribution with positive/negative drivers, omitted terms, and feature context.
- dashboard Explore page for catalog-backed feature observations.

### Post-upgrade verification

Recommended checks after upgrade:

```bash
curl -fsS http://127.0.0.1:8000/api/metrics/catalog
curl -fsS "http://127.0.0.1:8000/api/features?device=preferred&metric_key=sleep.total_minutes&include_baseline=true"
curl -fsS "http://127.0.0.1:8000/api/insights/current?device=preferred"
```

The bracelet does not need to be nearby for these checks; they replay from existing SQLite history.

## Technical-debt cleanup opportunities in this sprint

- Centralize metric metadata instead of scattering labels/units across dashboard cards.
- Move relationship math into small, testable Python helpers independent of FastAPI.
- Use long-form feature observations for trends/correlations instead of adding raw-table-specific endpoint branches.
- Expand analytic-surface validation from selected views to all views consumed by new endpoints.
- Preserve compatibility views while directing new code to richer feature-store names.
