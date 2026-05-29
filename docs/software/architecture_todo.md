# Architecture Hardening TODO

This backlog tracks the remaining work to fully align the codebase with
the software architecture.

Source architecture:

- [Software Architecture](/Users/remi.turpaud/Code/h59/docs/software/architecture.md:1)

## Completed

The following hardening items are now materially in place:

- clear runtime split:
  - `Integration Runtime` for the CLI package
  - `Serving Runtime` for the API and dashboard
- explicit UTC-at-rest policy in storage and documentation
- analytic SQL views created in the shared SQLite database
  - heart-rate intervals
  - activity intervals
  - sleep-stage intervals
  - SpO2 intervals
  - HRV intervals
  - pressure/stress intervals
  - daily activity and sleep projections
- dashboard API device-resolution boilerplate reduced into shared helpers
- dashboard API payload logic split into domain modules under `dashboard/api/src/h59_dashboard_api/payloads/`
- dashboard API range filtering moved away from silent `date(timestamp)` semantics toward explicit UTC range predicates in the main product paths
- dashboard API now exposes explicit time-context metadata in its response contract
- dashboard UI now displays the current time policy in the header
- UTC day-boundary behavior is covered by regression tests
- page-level dashboard charts standardized on Apache ECharts
- transitional page-level chart components removed
- frontend data access centralized through reusable hooks
- heavy route pages lazy-loaded to improve bundle structure

## Remaining High-Priority Work

### 1. Time Semantics

- add regression tests for local-day versus UTC-day behavior in dashboard/API interactions
  - current state: UTC day-boundary behavior is covered, but local-display edge cases still need broader coverage

### 2. Analytic Layer Depth

- expand the analytic layer beyond interval projections into named analytic entities
  - completeness projections
  - valid-time aggregations for common dashboard reads
  - clearer distinction between measured, derived, estimated, and provisional entities
- document which views are authoritative for each dashboard metric
- decide when query-time computation remains acceptable and when materialization becomes justified

### 3. API Cleanup

- separate SQL access helpers from payload assembly more aggressively
- add a small internal contract for common response metadata
  - time semantics
  - trust semantics
  - freshness semantics
- add more endpoint-level tests around analytic-view usage and range behavior

### 4. Visualization Consistency

- decide whether card sparklines remain custom SVG or also move to ECharts
- extract shared ECharts theme/config helpers further so `TimeSeriesChart` and trend pages share more option-building logic
- standardize empty-state messaging and degraded-data messaging across all pages

### 5. Accessibility and UX Robustness

- audit chart interactions for keyboard and touch usability
- add more visible focus states and chart descriptions
- review mobile usability for hover-dependent charts and provide touch-friendly fallbacks where needed

### 6. Performance

- reduce the remaining large vendor chunk from ECharts
  - current route splitting helps, but the base bundle is still heavy
- benchmark dashboard API latency against larger local databases
- add supporting indexes if real query latency warrants them

### 7. Testing

- add frontend route-level tests for:
  - loading
  - error
  - empty states
  - device switching
  - shared time-range behavior
- add analytic-boundary tests for the new SQLite views
- add tooltip/range regression tests for the chart layer where practical

### 8. Documentation

- update the visualization architecture doc to remove references to superseded components and files
- split software documentation more explicitly into:
  - integration/storage
  - analytics
  - API
  - visualization

## Acceptance Criteria

This hardening backlog is materially complete when:

- analytic meaning is defined once and reused by the API and dashboard
- the API is mostly transport and response shaping, not business interpretation
- all comparable charts use explicit and shared time semantics
- visualization behavior is consistent across pages
- provisional data remains visible and explainable
- the codebase is easier to extend than the original prototype
