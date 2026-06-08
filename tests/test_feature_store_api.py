from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboard" / "api" / "src"))

from h59_dashboard_api.config import Settings  # noqa: E402
from h59_dashboard_api.main import create_app  # noqa: E402
from h59_dashboard_api.payloads.common import ensure_analytic_surface  # noqa: E402
from h59_client.storage import H59Database  # noqa: E402


def _seed_history(path: Path) -> int:
    db = H59Database(path)
    device_id = db.upsert_device(
        address="AA:BB:CC:DD:EE:FF",
        name="H59",
        advertisement=None,
        hw_version="H59_V2.2",
        fw_version="H59_2.20.02_260319",
        last_seen_at=datetime(2026, 6, 8, 8, 0, tzinfo=UTC),
    )
    metric_systolic = db._ensure_metric_code("health-check.systolic", label="Systolic", unit="mmHg")
    metric_diastolic = db._ensure_metric_code("health-check.diastolic", label="Diastolic", unit="mmHg")
    base = datetime(2026, 5, 25, 8, 0, tzinfo=UTC)
    for offset in range(15):
        day = base + timedelta(days=offset)
        sync_id = db.create_sync(device_id, started_at=day, source="test")
        db.finish_sync(sync_id, finished_at=day + timedelta(minutes=10))
        # Daily HR/HRV/pressure/activity vary enough for trends and correlations.
        db.connection.execute(
            "INSERT INTO heart_rates(device_id, sync_id, timestamp, reading, source_command, raw_packet_hex) VALUES (?, ?, ?, ?, 21, '')",
            (device_id, sync_id, (day + timedelta(hours=1)).isoformat(), 58 + offset % 4),
        )
        db.connection.execute(
            "INSERT INTO hrv_samples(device_id, sync_id, timestamp, sample_index, value, interval_minutes, source_command, raw_packet_hex) VALUES (?, ?, ?, 0, ?, 30, 57, '')",
            (device_id, sync_id, (day + timedelta(hours=2)).isoformat(), 45 + offset),
        )
        db.connection.execute(
            "INSERT INTO pressure_samples(device_id, sync_id, timestamp, sample_index, value, interval_minutes, source_command, raw_packet_hex) VALUES (?, ?, ?, 0, ?, 30, 55, '')",
            (device_id, sync_id, (day + timedelta(hours=3)).isoformat(), 35 + (offset % 5)),
        )
        db.connection.execute(
            "INSERT INTO sport_details(device_id, sync_id, timestamp, time_index, steps, distance, calories, source_command, raw_packet_hex) VALUES (?, ?, ?, 0, ?, ?, ?, 67, '')",
            (device_id, sync_id, (day + timedelta(hours=4)).isoformat(), 4000 + offset * 500, 3000 + offset * 300, 120 + offset * 10),
        )
        sleep_start = day - timedelta(hours=10)
        sleep_end = day - timedelta(hours=3)
        db.connection.execute(
            "INSERT INTO sleep_sessions(device_id, sync_id, start_timestamp, end_timestamp, total_minutes, state, score, is_provisional, source_command, raw_json) VALUES (?, ?, ?, ?, 420, 'sleep', ?, 0, 39, ?)",
            (device_id, sync_id, sleep_start.isoformat(), sleep_end.isoformat(), 78 + offset % 10, f'{{"day": {offset}}}'),
        )
        sleep_session_id = int(db.connection.execute("SELECT MAX(sleep_session_id) FROM sleep_sessions").fetchone()[0])
        stages = [("deep", 90), ("rem", 80), ("light", 220), ("awake", 30)]
        cursor = sleep_start
        for i, (stage, minutes) in enumerate(stages):
            end = cursor + timedelta(minutes=minutes)
            db.connection.execute(
                "INSERT INTO sleep_stage_samples(sleep_session_id, device_id, sync_id, sequence_index, stage, start_timestamp, end_timestamp, minutes, is_provisional, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, '{}')",
                (sleep_session_id, device_id, sync_id, i, stage, cursor.isoformat(), end.isoformat(), minutes),
            )
            cursor = end
        db.connection.execute(
            "INSERT INTO blood_oxygen_samples(device_id, sync_id, timestamp, sample_index, min_percent, max_percent, interval_minutes, is_provisional, source_command, raw_packet_hex) VALUES (?, ?, ?, 0, 94, 98, 30, 0, 42, '')",
            (device_id, sync_id, (day + timedelta(hours=5)).isoformat()),
        )
        if offset in {5, 10, 14}:
            packet = f"bp-{offset}"
            ts = day + timedelta(hours=6)
            db.connection.execute(
                "INSERT INTO realtime_samples(device_id, sync_id, timestamp, metric_code_id, value_numeric, value_text, error_code, source_command, raw_packet_hex, metric, value) VALUES (?, ?, ?, ?, ?, NULL, 0, 99, ?, 'health-check.systolic', ?)",
                (device_id, sync_id, ts.isoformat(), metric_systolic, 118 + offset, packet, str(118 + offset)),
            )
            db.connection.execute(
                "INSERT INTO realtime_samples(device_id, sync_id, timestamp, metric_code_id, value_numeric, value_text, error_code, source_command, raw_packet_hex, metric, value) VALUES (?, ?, ?, ?, ?, NULL, 0, 99, ?, 'health-check.diastolic', ?)",
                (device_id, sync_id, ts.isoformat(), metric_diastolic, 76 + offset, packet, str(76 + offset)),
            )
    db.connection.commit()
    db.close()
    return device_id


def _client(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "h59.sqlite"
    _seed_history(db_path)
    app = create_app(Settings(db_path=db_path, read_only=False, host="127.0.0.1", port=8000, cors_origins=("*",)))
    return TestClient(app)


def test_feature_store_views_rebuild_stale_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "h59.sqlite"
    _seed_history(db_path)
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        ensure_analytic_surface(conn)
        conn.executescript("DROP VIEW health_feature_observations; CREATE VIEW health_feature_observations AS SELECT 1 AS old_column;")
        ensure_analytic_surface(conn)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(health_feature_observations)")}
    assert {"feature_name", "feature_value", "confidence", "observation_as_of"}.issubset(columns)


def test_metric_catalog_and_features_endpoints(tmp_path: Path) -> None:
    client = _client(tmp_path)
    catalog = client.get("/api/metrics/catalog", params={"dashboard_default": "true"})
    assert catalog.status_code == 200
    metrics = catalog.json()["metrics"]
    keys = {m["metric_key"] for m in metrics}
    assert {"hr.resting_sleep_bpm", "hrv.daily_median", "sleep.efficiency_pct", "activity.steps_total", "bp.latest_systolic"}.issubset(keys)
    hrv = next(m for m in metrics if m["metric_key"] == "hrv.daily_median")
    assert hrv["approximation_level"] == "vendor-derived"

    features = client.get("/api/features", params=[("metric_key", "sleep.efficiency_pct"), ("include_baseline", "true")])
    assert features.status_code == 200
    payload = features.json()
    assert payload["series"][0]["metric_key"] == "sleep.efficiency_pct"
    assert payload["series"][0]["observations"]
    assert "baseline" in payload["series"][0]["observations"][-1]

    daily = client.get("/api/features/daily", params={"date": "2026-06-08"})
    assert daily.status_code == 200
    body = daily.json()
    assert body["feature_date"] == "2026-06-08"
    assert body["features"]["sleep.efficiency_pct"]["value"] > 0


def test_current_insight_includes_driver_attribution(tmp_path: Path) -> None:
    client = _client(tmp_path)
    response = client.get("/api/insights/current")
    assert response.status_code == 200
    payload = response.json()
    assert "readiness" in payload
    assert "components" in payload["readiness"]
    assert payload["readiness"]["drivers_positive"] or payload["readiness"]["drivers_negative"]
    assert "feature_context" in payload


def test_sleep_strain_trends_correlations_and_behavior_effects(tmp_path: Path) -> None:
    client = _client(tmp_path)
    sleep = client.get("/api/sleep/summary", params={"date": "2026-06-08", "include_stages": "true"})
    assert sleep.status_code == 200
    sleep_body = sleep.json()
    assert sleep_body["sessions"][0]["derived"]["restorative_minutes"] == 170
    assert "stage_percentages" in sleep_body["sessions"][0]["derived"]

    strain = client.get("/api/strain/daily")
    assert strain.status_code == 200
    assert strain.json()["days"]

    workouts = client.get("/api/workouts")
    assert workouts.status_code == 200
    assert workouts.json()["bouts"]

    trends = client.get("/api/trends", params=[("metric_key", "activity.steps_total"), ("window", "7")])
    assert trends.status_code == 200
    assert trends.json()["series"][0]["points"][-1]["rolling_avg"] is not None

    compare = client.get("/api/compare", params=[("metric_key", "sleep.total_minutes"), ("metric_key", "hrv.daily_median")])
    assert compare.status_code == 200
    assert compare.json()["aligned_points"]

    corr = client.get("/api/correlations", params={"x_metric_key": "sleep.total_minutes", "y_metric_key": "hrv.daily_median", "lag_days": "0"})
    assert corr.status_code == 200
    assert corr.json()["sample_count"] >= 10
    assert "interpretation" in corr.json()

    effects = client.get("/api/behavior-effects", params={"event_key": "high-step-day", "target_metric_key": "sleep.total_minutes", "lag_days": "0"})
    assert effects.status_code == 200
    assert "explanation" in effects.json()
