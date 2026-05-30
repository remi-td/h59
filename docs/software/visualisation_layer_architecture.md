# H59 Local Health Web Dashboard — Architecture Recommendation

## 1. Purpose

This document updates the dashboard architecture for the `h59` project.

The recommendation is to build a lightweight, mobile-first web application that displays personal health KPIs in a clear card-based interface.

The core principle is separation of concerns:

```text
h59 CLI / sync tool = device integration, BLE, protocol, storage
web dashboard       = read-only API, visualisation, local health interface
```

The dashboard should remain separate from the core CLI package. It should consume the local SQLite database produced by the CLI and must not contain BLE or protocol logic.

## 2. Current Project Context

The existing project is a local-first CLI for collecting and analysing data from the H59 smart band.

The current repository already provides:

- BLE device discovery and registration.
- One-shot and incremental sync into SQLite.
- Detached periodic sync daemon.
- Storage of decoded measurements and raw protocol packets.
- Device actions such as vibration and reboot.
- Markdown report generation.
- Documentation split between software docs and reverse-engineering notes.

Current repository layout:

```text
src/h59_client/     installable CLI package
tests/              unit tests
tools/              project utilities
docs/software/      user-facing software documentation
docs/research/      reverse-engineering findings
data/               runtime databases and generated outputs, not tracked
```

The dashboard architecture should preserve this structure and avoid turning the CLI into a web application.

## 3. Recommended High-Level Architecture

```text
H59 bracelet
    ↓ BLE
h59 CLI / daemon
    ↓ writes local data
SQLite database
    ↓ read-only access
FastAPI dashboard API
    ↓ JSON
Responsive web app / PWA
    ↓ browser
Desktop and mobile users
```

The recommended stack is:

| Layer | Recommendation | Reason |
|---|---|---|
| Device sync | Existing `h59` CLI | Already handles BLE/protocol/local storage |
| Storage | SQLite | Simple, local, single-user, already used by the project |
| API | FastAPI | Python-native, simple, agent-friendly |
| Frontend | React/Vite or SvelteKit | Good mobile-first web application foundations |
| Charts | Apache ECharts or lightweight chart library | Flexible health-style visualisations |
| Deployment | Separate dashboard service | Keeps CLI package clean |
| Optional packaging | Docker Compose | Simple local deployment |

## 4. Repository Structure Recommendation

Add a new top-level `dashboard/` directory.

Do not place web dashboard code inside `src/h59_client/`.

Recommended structure:

```text
h59/
  src/
    h59_client/
      # existing CLI, BLE, protocol, storage, reporting

  docs/
    software/
      # existing CLI/user documentation
      dashboard_architecture.md
    research/
      # protocol/device research

  data/
    h59.sqlite

  dashboard/
    README.md

    api/
      pyproject.toml
      src/
        h59_dashboard_api/
          __init__.py
          main.py
          config.py
          db.py
          queries.py
          schemas.py
          analytics.py

    web/
      package.json
      index.html
      src/
        main.tsx
        App.tsx
        pages/
          Today.tsx
          Trends.tsx
          Sleep.tsx
          Heart.tsx
          Oxygen.tsx
          Activity.tsx
          Device.tsx
          Debug.tsx
        components/
          MetricCard.tsx
          Sparkline.tsx
          TrendEChart.tsx
          TimeSeriesChart.tsx
          SleepTimeline.tsx
          TrustBadge.tsx
          DataQualityBadge.tsx
          PageHeader.tsx
        api/
          client.ts
          types.ts

    docker-compose.yml
```

Alternative simpler first version:

```text
dashboard/
  app.py               # Streamlit prototype
  README.md
```

However, if the goal is a durable mobile-friendly web app, the preferred long-term path is:

```text
FastAPI + React/Vite or SvelteKit
```

## 5. Component Boundaries

## 5.1 Core CLI: `src/h59_client/`

The core CLI remains responsible for:

- BLE scanning.
- Device registration.
- Device selection and nicknames.
- H59 protocol implementation.
- One-shot sync.
- Incremental sync.
- Detached periodic sync daemon.
- Raw packet storage.
- Decoded measurement storage.
- Device actions: vibrate, reboot, capabilities.
- CLI reports.

The core CLI should not:

- Serve HTTP.
- Contain frontend code.
- Depend on Node.js.
- Depend on dashboard-specific packages.
- Format data for a specific web UI beyond stable tables or documented query surfaces.

## 5.2 Dashboard API: `dashboard/api/`

The dashboard API is a read-mostly service over the SQLite database.

Responsibilities:

- Open the existing H59 SQLite database.
- Expose clean JSON endpoints for dashboard use.
- Provide summary and trend queries.
- Hide raw database complexity from the frontend.
- Label metric trust levels.
- Provide data-quality information.

The dashboard API should not:

- Connect to the H59 device.
- Implement BLE protocol logic.
- Mutate raw device records.
- Become the source of truth.

Optional write operations may be added later for dashboard preferences only, such as hidden cards or display settings. These should be stored separately from core device data.

## 5.3 Web App: `dashboard/web/`

The web app is a responsive browser interface.

Responsibilities:

- Display today’s KPIs as cards.
- Show detail pages for each metric.
- Provide trend charts.
- Show data-quality and device status.
- Work well on mobile browsers.
- Optionally support PWA installation.

The web app should not:

- Read SQLite directly.
- Contain health analytics logic beyond simple display transforms.
- Know about BLE or protocol internals.

## 6. Data Flow

```text
1. User runs sync manually or daemon runs periodically:

   h59 sync -i
   h59 sync -di --period 15m

2. CLI writes data to SQLite:

   ./data/h59.sqlite
   or
   $XDG_DATA_HOME/h59/h59.sqlite

3. Dashboard API reads SQLite in read-only mode.

4. Frontend calls API endpoints.

5. Browser renders mobile-first health cards and charts.
```

## 7. Database Access Strategy

The dashboard should treat the CLI-created SQLite database as the source of truth.

Recommended access mode:

```text
read-only by default
```

Example configuration:

```env
H59_DB_PATH=../../data/h59.sqlite
H59_DASHBOARD_READONLY=true
```

The API should gracefully handle:

- Missing database file.
- Empty database.
- No registered device.
- No sync yet.
- Stale data.
- Multiple registered devices.

## 8. API Design

Keep the API small and stable.

Recommended endpoints:

```http
GET /api/health
GET /api/devices
GET /api/today?device_id=1
GET /api/metrics/steps?device_id=1&range=30d
GET /api/metrics/heart-rate?device_id=1&range=24h
GET /api/metrics/hrv?device_id=1&range=30d
GET /api/metrics/spo2?device_id=1&range=30d
GET /api/metrics/stress?device_id=1&range=30d
GET /api/metrics/blood-pressure?device_id=1&range=30d
GET /api/sleep?device_id=1&range=30d
GET /api/activity/sport-sessions?device_id=1&range=30d
GET /api/device/status?device_id=1
GET /api/data-quality?device_id=1&range=30d
```

## 8.1 Example `/api/today` Response

```json
{
  "date": "2026-05-29",
  "device": {
    "id": 1,
    "nickname": "wristband",
    "battery_percent": 83,
    "last_sync": "2026-05-29T08:12:00Z",
    "data_freshness": "fresh"
  },
  "cards": [
    {
      "id": "steps",
      "title": "Steps",
      "value": 5842,
      "unit": "steps",
      "trust_class": "derived",
      "trend": "+1200 vs 30-day median"
    },
    {
      "id": "heart_rate",
      "title": "Heart Rate",
      "value": 78,
      "unit": "bpm",
      "trust_class": "measured",
      "summary": {
        "min": 54,
        "max": 112,
        "avg": 73
      }
    },
    {
      "id": "sleep",
      "title": "Sleep",
      "value": 417,
      "unit": "minutes",
      "display_value": "6 h 57 min",
      "trust_class": "derived"
    },
    {
      "id": "spo2",
      "title": "Blood Oxygen",
      "value": 97,
      "unit": "%",
      "trust_class": "derived"
    },
    {
      "id": "hrv",
      "title": "HRV",
      "value": 48,
      "unit": "ms",
      "trust_class": "derived"
    },
    {
      "id": "blood_pressure",
      "title": "Blood Pressure Estimate",
      "value": "118/78",
      "unit": "mmHg",
      "trust_class": "estimated"
    }
  ]
}
```

## 9. UI Design Principles

The interface should be:

- Mobile-first.
- Card-based.
- Calm and readable.
- Metric-focused.
- Clear about trust level.
- Clear about stale or missing data.
- Optimized for quick daily review.
- Capable of drilling into detail pages.

## 9.1 Primary Navigation

Recommended pages:

| Page | Purpose |
|---|---|
| Today | Main card overview |
| Trends | 7-day and 30-day views |
| Sleep | Sleep duration, window, segments, night HR |
| Heart | Heart rate, HRV, resting/night HR |
| Oxygen | SpO₂ latest, range, night minimum |
| Activity | Steps and sport sessions |
| Device | Battery, sync, data quality |
| Debug | Raw sample counts and diagnostics |

## 9.2 Main Cards

The Today page should include:

- Steps.
- Heart rate.
- Sleep.
- Blood oxygen.
- HRV.
- Stress.
- Blood pressure estimate.
- Sport/activity summary.
- Battery.
- Last sync.

## 9.3 Metric Trust Labels

Every card should display a small trust badge.

Recommended values:

```text
Measured
Derived
Estimated
Vendor score
Unknown
```

Recommended mapping:

| Metric | Trust badge |
|---|---|
| Heart rate | Measured |
| Steps | Derived |
| SpO₂ | Derived |
| HRV | Derived |
| Sleep duration | Derived |
| Sleep stages | Vendor score |
| Stress | Vendor score |
| Blood pressure | Estimated |
| Calories | Estimated |
| One-key score | Vendor score |

## 10. Chart Components

Reusable chart components:

| Component | Use |
|---|---|
| `MetricCard` | Today overview card |
| `Sparkline` | Small inline card chart |
| `TrendEChart` | Reusable ECharts page-level wrapper |
| `TimeSeriesChart` | Heart rate, SpO₂, HRV, stress |
| `SleepTimeline` | Sleep session and stages |
| `TrendSummary` | Baseline comparison |
| `TrustBadge` | Measurement confidence |
| `DataQualityBadge` | Fresh/partial/stale status |

Recommended chart library:

```text
Apache ECharts
```

Reasons:

- Good time-series support.
- Good mobile interaction.
- Flexible enough for health-style visualisations.
- Easy to drive from JSON data.

Simpler alternative:

```text
uPlot or Recharts
```

## 11. Analytics Strategy

Keep analytics simple and transparent.

## 11.1 Version 1 Analytics

Version 1 should reproduce the vendor app metrics and show them clearly.

Required summaries:

- Latest heart rate.
- Heart-rate min / max / average.
- Total daily steps.
- Sleep duration.
- Sleep start and end.
- Latest SpO₂.
- Latest HRV.
- Latest stress score.
- Latest blood-pressure estimate.
- Device battery.
- Last sync.

## 11.2 Version 2 Analytics

Add local baselines:

```text
7-day median
30-day median
90-day median
```

For:

- Sleep duration.
- Night heart rate.
- HRV.
- Steps.
- SpO₂ minimum.

Add deviation summaries:

```text
-42 min vs 30-day median
+5 bpm vs 30-day median
-12 ms vs 30-day median
```

## 11.3 Data Quality

Data quality should be first-class.

Expose:

- Last successful sync.
- Last sample timestamp.
- Battery level.
- Heart-rate samples today.
- SpO₂ samples today.
- HRV samples today.
- Sleep record present for previous night.
- Missing metrics.
- Stale data warning.

Suggested quality classes:

```text
fresh
partial
stale
empty
error
```

## 12. Deployment Options

## 12.1 Development Mode

Run API:

```bash
cd dashboard/api
uv run fastapi dev src/h59_dashboard_api/main.py
```

Run web app:

```bash
cd dashboard/web
npm install
npm run dev
```

## 12.2 Local Production Mode

Use Docker Compose under `dashboard/`.

```yaml
services:
  api:
    build: ./api
    container_name: h59-dashboard-api
    restart: unless-stopped
    environment:
      - H59_DB_PATH=/data/h59.sqlite
      - H59_DASHBOARD_READONLY=true
    volumes:
      - ../data:/data:ro
    ports:
      - "8000:8000"

  web:
    build: ./web
    container_name: h59-dashboard-web
    restart: unless-stopped
    environment:
      - H59_API_BASE_URL=http://api:8000
    ports:
      - "8080:80"
    depends_on:
      - api
```

For a single-host local setup, the web container can proxy `/api` to the API container.

## 13. Security and Privacy

The dashboard must remain local-first.

Requirements:

- No external analytics.
- No vendor cloud dependency.
- No third-party telemetry.
- No unauthenticated exposure to the public internet.
- Default bind should be localhost or LAN-only.
- Optional simple authentication if exposed beyond localhost.
- Database mounted read-only for dashboard API where possible.

Recommended default:

```text
localhost-only during development
LAN-only for trusted home network
VPN-only for remote access
```

## 14. Optional PWA Support

The web app may support installation to a phone home screen.

PWA features:

- Manifest file.
- Local icon.
- Responsive layout.
- Offline shell caching.
- No background cloud sync.

Do not add push notifications in version 1.

## 15. Testing Strategy

## 15.1 API Tests

Add tests for:

- Empty database response.
- Missing database response.
- Today endpoint.
- Metric range endpoints.
- Data quality endpoint.
- Multiple device handling.

## 15.2 Frontend Tests

Add tests for:

- Rendering cards with complete data.
- Rendering cards with missing data.
- Rendering estimated/vendor badges.
- Mobile layout snapshot.

## 15.3 Mock Data

Create a small mock database or fixture generator:

```text
tools/generate_mock_health_data.py
```

This allows dashboard development before real H59 data is fully stable.

## 16. MVP Acceptance Criteria

The MVP is complete when:

- The core CLI remains independent and unchanged in responsibility.
- Dashboard code lives outside `src/h59_client/`.
- API can read the local SQLite database.
- Web app runs in a browser and mobile browser.
- Today page displays:
  - steps,
  - heart rate,
  - sleep duration,
  - SpO₂,
  - HRV,
  - stress,
  - blood-pressure estimate,
  - battery,
  - last sync.
- Metric trust badges are visible.
- Missing data is handled gracefully.
- Device/data-quality page exists.
- No vendor cloud service is required for dashboard operation.

## 17. Recommended Build Order

1. Keep `src/h59_client/` focused on CLI, BLE, protocol, and storage.
2. Create `dashboard/` root directory.
3. Implement FastAPI read-only API over existing SQLite database.
4. Add mock data support.
5. Build Today page with static mock API response.
6. Connect Today page to real API.
7. Add metric detail pages.
8. Add charts.
9. Add data-quality page.
10. Add PWA support.
11. Add baseline analytics.
12. Keep the visualization stack focused on the web application and avoid parallel dashboarding systems.

## 18. Deliberate Non-Goals for Version 1

Do not build these in version 1:

- Full user account system.
- Multi-user support.
- Public internet deployment.
- Complex medical interpretation.
- Cloud sync.
- Vendor-app integration.
- Custom BLE logic in the dashboard.
- A second dashboarding stack in parallel with the web application.
- PostgreSQL or TimescaleDB unless SQLite becomes limiting.

## 19. Final Recommendation

Use the following structure:

```text
Core sync product:
  src/h59_client/

Local database:
  data/h59.sqlite

Dashboard product:
  dashboard/api/     FastAPI read-only API
  dashboard/web/     mobile-first health dashboard
```

Use SQLite as the first dashboard data source.

Use a browser/mobile responsive web app as the primary interface.

Keep the core CLI small, reliable, and independent from the dashboard.
