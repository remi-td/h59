# Dashboard Requirements

This document defines the target local dashboard built on top of the H59 SQLite database.

Status:
- this is a product requirement document
- it is not the current implementation

## Objective

Build a local dashboard that reproduces the key health and activity information shown by the bracelet ecosystem, while keeping collection and analytics private and self-hosted.

## Scope

The dashboard should cover:
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

## Core KPI Cards

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
