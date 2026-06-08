# Dashboard Requirements

This document defines the target local dashboard built on top of the H59 SQLite database.

Status:
- this is a product requirement document
- it also records the implemented dashboard surfaces where relevant

## Objective

Build a local dashboard that reproduces the key health and activity information shown by the bracelet ecosystem, while keeping collection and analytics private and self-hosted.

## Scope

The dashboard should cover:
- health-insight summary and coaching guardrails
- daily activity
- heart rate
- sleep
- blood oxygen / SpO2
- HRV
- stress
- blood pressure estimate
- sport / exercise records
- device status and sync quality

## First-Version Priorities

1. Faithful display of the data that is actually stored locally.
2. Clear distinction between measured, derived, and estimated metrics.
3. Explicit visibility into sync quality and missing data.
4. Clear confidence and safety guardrails for any health/coaching summary.

## Core KPI Cards

- Health Insights summary
- Readiness score
- Sleep score
- Strain score
- Daily overview
- Heart rate
- Sleep
- Blood oxygen
- Blood pressure
- HRV
- Stress
- Sport / activity records
- Device and sync status

## Trust Labels

Recommended labels:
- `Measured`
- `Derived`
- `Estimated`
- `Vendor score`

For the Health Insights page specifically, the API must also expose a confidence level and explain why the current-state summary is more or less trustworthy.

## Implemented Health Insights Surface

The dashboard default route is the Health Insights page. It is backed by:

```text
GET /api/insights/current?device=preferred
```

The endpoint uses only the local SQLite store. It computes deterministic, explainable scores from reusable feature views and Python scoring logic:

- `health_daily_features`: day-level reusable physiological/activity/sleep features
- `health_metric_observations`: normalized metric observations suitable for baselines
- `health_metric_baselines`: rolling 7/14/30/60-day local baselines
- `dashboard/api/src/h59_dashboard_api/insights.py`: readiness, sleep, strain, state, recommendation, safety flags, and LLM guardrails

The output must include sync context so consumers do not mistake stale bracelet data for current physiology.

The insight surface is not diagnostic. It should avoid medical claims and should tell users to confirm abnormal BP/SpO2 wearable observations with appropriate trusted measurements.

## Time Views

Minimum viable support:
- today
- yesterday
- last 7 days
- last 30 days
- custom date range

## Output Requirement

The dashboard should be built from the local SQLite store only.

It must not depend on vendor cloud services.
