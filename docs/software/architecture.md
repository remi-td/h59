# H59 Software Architecture

## Purpose

This document defines the software architecture for `h59-local`.

The goal is to:

- separate device integration from analytics, API, and presentation concerns
- preserve raw collected data with minimal transformation
- keep analytics and presentation stateless where practical
- make the project easier to maintain, test, and evolve

This architecture supersedes ad hoc design decisions made during reverse-engineering and dashboard prototyping and now materially matches the current implementation.

## Design Principles

The system follows these principles:

- `Raw-first`: if the device exposes data, store it locally and keep it.
- `Touch it, take it`: collection should not discard or reinterpret information unless required for basic typing and timestamp normalization.
- `Append and preserve`: raw evidence should remain available even when higher-level interpretations change.
- `Layered responsibilities`: each module has a clear contract and should not absorb adjacent concerns.
- `Stateless consumers`: analytics, API, and visualization should recompute from source data at query time unless the cost is clearly prohibitive.
- `Feature-store first`: reusable feature observations and daily feature rows are the analytics contract; dashboard cards should not grow bespoke raw-table calculations.
- `Operational simplicity`: prefer SQLite views plus Python scoring over daemon-time materialization until measured latency proves otherwise.
- `UTC at rest`: timestamps are stored in UTC in the database; display-local time is a presentation concern.
- `Valid-time analytics`: derived temporal entities are represented as valid `[from, to[` intervals.
- `Confidence over certainty`: wellness scores must expose provenance, approximation level, confidence, and omitted inputs.

## High-Level Architecture

```text
H59 device
    ↓ BLE
1. Device module
    ↓ writes raw and minimally typed local data
SQLite database
    ↓ analytic views / derived projections
2. Analytic module
    ↓ stateless query surface
3. API module
    ↓ JSON / HTTP
4. Visualization module
    ↓ browser / app UI
User
```

Current physical deployment:

```text
Integration Runtime
  h59 CLI package
  - Device module
  - Analytic module

Serving Runtime
  dashboard service
  - API module
  - Visualization module

Shared backend
  SQLite
```

This split is the current implementation shape.

## Module 1: Device Module

### Purpose

The Device module is responsible for communicating with the wearable and collecting locally stored data.

### Current implementation boundary

Current code location:

```text
src/h59_client/
```

This includes:

- BLE discovery
- device registration
- direct BLE actions
- protocol framing and parsing
- sync orchestration
- SQLite persistence of collected device data

### Responsibilities

- discover devices
- identify and register devices
- connect over BLE
- issue device commands
- read supported protocol surfaces
- persist collected data into the local storage backend
- persist raw packets and raw protocol evidence when available
- normalize only the minimal technical concerns required for storage:
  - data types
  - timestamp normalization to UTC
  - basic packet decoding needed to land observations in tables

### Non-responsibilities

The Device module must not:

- implement dashboard formatting
- implement user-facing analytics
- perform opinionated health scoring
- apply user-facing imputation or smoothing logic
- delete historical evidence because a newer interpretation exists

### Storage policy

The Device module follows:

`touch it, take it`

Meaning:

- collect as much data as the device makes available
- preserve raw packets or raw JSON evidence when possible
- avoid destructive transformations
- avoid incremental cleanup logic beyond technical integrity fixes

### Data model expectations

The Device layer primarily deals with:

- reference data
  - devices
  - capabilities
  - settings
  - GATT metadata
- event or sample data
  - heart-rate samples
  - activity summaries
  - sleep sessions and stage periods
  - blood oxygen samples
  - pressure / stress-like samples
  - HRV samples
- protocol evidence
  - raw packets
  - raw JSON payloads

Temporal shape at this layer is usually:

- point-in-time samples, or
- device-native grouped observations

This layer is not required to expose a normalized business-temporal model.

## Module 2: Analytic Module

### Purpose

The Analytic module transforms collected device data into consumer-oriented analytic entities.

This is a logical module even when it is packaged with the CLI application.

### Responsibilities

- expose stable analytic representations over collected device data
- normalize different device-native shapes into usable temporal entities
- compute derived metrics when needed
- compute data quality and completeness views
- perform extrapolation or adjustment only when explicitly defined
- serve as the source layer for API consumption

### Key temporal model

The canonical temporal representation for analytics is:

`valid [from, to[`

Examples:

- sleep stage valid from `23:40` to `01:05`
- activity summary valid from `07:00` to `08:00`
- average heart rate valid from `10:00` to `10:05`

This differs from the Device layer, where observations may be stored in the device-native representation first.

### Statelessness policy

The Analytic layer should remain stateless by default:

- recompute at query time when practical
- prefer database views or query-layer projections
- avoid background materialization jobs unless the runtime cost becomes clearly unacceptable

This trades some runtime cost for:

- simpler maintenance
- fewer synchronization bugs
- fewer partial refresh states
- easier correction when decoding rules improve

### Current implementation form

For now, this module may live in the same SQLite database as the Device layer using:

- SQL views
- query helpers
- lightweight Python aggregation functions

This is an implementation convenience, not a collapse of responsibilities.

### Non-responsibilities

The Analytic module must not:

- own BLE communication
- own presentation rules
- embed API routing concerns
- become a client-specific formatting layer

## Module 3: API Module

### Purpose

The API module exposes analytic data to downstream consumers.

### Current implementation boundary

Current code location:

```text
dashboard/api/
```

### Responsibilities

- expose analytic data via a stable API
- provide device and metric query endpoints
- provide data quality and freshness views
- remain stateless
- avoid embedding analytic business rules beyond request shaping

### Principles

- no BLE logic
- no SQLite mutation as part of normal reads
- no duplicated business logic that belongs in the analytic layer
- no frontend-specific logic unless the API explicitly defines that projection

### API style guidance

The API should:

- consume analytic entities rather than reconstructing metric meaning from raw device tables
- disclose time semantics clearly
- disclose freshness and trust metadata explicitly
- support stable selectors and range semantics

### Non-responsibilities

The API module must not:

- compute ad hoc dashboard-only analytics that bypass the analytic layer
- contain database-specific query duplication for every page
- own styling or view decisions

## Module 4: Visualization Module

### Purpose

The Visualization module presents the data to the user.

### Current implementation boundary

Current code location:

```text
dashboard/web/
```

### Responsibilities

- source all data from the API module
- present information clearly and attractively
- implement user interaction, navigation, charting, and display formatting
- remain stateless beyond local UI state
- be easy to customize

### Principles

- no BLE logic
- no SQLite access
- no metric business logic
- no data-repair or transformation logic that belongs upstream

### UX goals

The dashboard should:

- look professional and intentional
- be readable on desktop and mobile
- use a consistent page-level charting system
- clearly communicate time range, freshness, and trust
- avoid misleading comparisons

## Data Contracts Between Modules

## Device → Analytic

Contract:

- device-collected data is persisted durably
- timestamps are UTC
- raw evidence remains available where possible
- basic typing is applied

The Analytic module must be able to reinterpret stored data later without requiring recollection.

## Analytic → API

Contract:

- entities are stable and consumer-oriented
- temporal data is queryable in a predictable way
- derived semantics are explicit
- time range and timezone semantics are documented

## API → Visualization

Contract:

- responses are presentation-ready but not presentation-coupled
- time windows and units are explicit
- missing data, freshness, and trust levels are explicit
- the frontend should not need to infer hidden semantics

## Current Mapping to the Repository

## Integration Runtime

```text
src/h59_client/
  ble.py
  protocol.py
  sync.py
  storage.py
  analytics.py
  report.py
  cli.py
```

Logical mapping:

- Device module:
  - `ble.py`
  - `protocol.py`
  - `sync.py`
  - device-facing parts of `storage.py`
  - CLI action surface in `cli.py`
- Analytic module:
  - `analytics.py`
  - SQLite analytic views created by `storage.py` through `analytics.ensure_analytic_views()`
  - analytic/report-oriented parts of `report.py`
  - analytic query helpers over the shared SQLite database

## Serving Runtime

```text
dashboard/api/
dashboard/web/
```

Logical mapping:

- API module:
  - `dashboard/api/src/h59_dashboard_api/`
  - shared API helpers:
    - `device_context.py`
    - `time.py`
  - domain payload builders:
    - `payloads/`
- Visualization module:
  - `dashboard/web/src/`
  - reusable frontend data hooks:
    - `api/hooks.ts`
  - page-level chart framework:
    - Apache ECharts
  - card-level micro-visualizations:
    - custom sparklines and compact SVG components where appropriate

## Storage Architecture

For now, both logical data layers share the same SQLite database.

Conceptually:

```text
SQLite
  raw and minimally typed device tables
  analytic views / projections
```

This is acceptable because the boundary is explicit:

- base tables:
  - owned by Device module
- analytic views:
  - owned by Analytic module

The API currently prefers analytic views for its main metric and interval projections.

## Time Semantics

This architecture adopts the following rules:

- timestamps at rest are stored in UTC
- device sync logic normalizes timestamps to UTC before persistence
- analytics may define valid intervals using UTC bounds
- the API must disclose or encode its time semantics explicitly
- the UI may render in local time, but must do so consistently and visibly

Two especially important distinctions:

- `storage timezone`:
  - always UTC
- `display timezone`:
  - a visualization concern

## Evolution Rules

Future changes should follow these rules:

- if a change touches BLE or device interaction, it belongs in Module 1
- if a change changes metric meaning or data interpretation, it belongs in Module 2
- if a change only affects transport or endpoint shape, it belongs in Module 3
- if a change only affects display or interaction, it belongs in Module 4

When a change seems to span layers, split it deliberately instead of letting one module absorb the concern.

## Current Implementation Status

The current codebase now reflects these architectural decisions:

- the CLI package exposes a distinct analytic surface through SQLite views and analytic helpers
- the dashboard API is organized around shared device/time helpers plus domain payload modules
- the dashboard frontend uses reusable data hooks instead of route-by-route request orchestration
- page-level visualizations are standardized on one charting framework
- raw tables and analytic projections are separated conceptually within the shared SQLite backend
- API responses expose explicit time-context metadata
- the dashboard header makes the current display/storage/day-boundary time policy visible

## Non-Goals

This document does not:

- prescribe a future non-SQLite backend
- prescribe a specific analytical compute engine beyond the current stateless preference
- require immediate physical separation of the Device and Analytic modules
- require immediate deployment separation of API and Visualization

Those are implementation decisions that may evolve later without changing the logical architecture.
