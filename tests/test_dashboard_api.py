from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboard" / "api" / "src"))

import h59_dashboard_api.payloads.today as today_payload_module  # noqa: E402
import h59_dashboard_api.payloads.metrics as metrics_payload_module  # noqa: E402
from h59_dashboard_api.config import Settings  # noqa: E402
from h59_dashboard_api.main import create_app  # noqa: E402
from h59_client.protocol import BatteryStatus  # noqa: E402
from h59_client.storage import H59Database, RealtimeObservation  # noqa: E402


def _seed_db(path: Path) -> None:
    db = H59Database(path)
    now = datetime(2026, 5, 29, 12, 0, tzinfo=UTC)
    device_id = db.upsert_device(
        address="00:11:22:33:44:55",
        name="H59",
        advertisement=None,
        hw_version="H59_V2.2",
        fw_version="H59_2.20.02_260319",
        last_seen_at=now,
    )
    sync_id = db.create_sync(device_id, started_at=now, source="test")
    db.connection.execute(
        "INSERT INTO syncs(sync_id, comment, device_id, timestamp, finished_at, source) VALUES (?, ?, ?, ?, ?, ?)",
        (sync_id + 1, None, device_id, now.isoformat(), now.isoformat(), "test"),
    )
    db.record_battery(device_id, sync_id, timestamp=now, sample=BatteryStatus(battery_level=82, charging=False), raw_packet_hex="")
    db.connection.execute(
        "INSERT INTO heart_rates(reading, timestamp, device_id, sync_id, source_command, raw_packet_hex) VALUES (72, ?, ?, ?, 21, '')",
        (now.isoformat(), device_id, sync_id),
    )
    db.connection.execute(
        "INSERT INTO sport_details(calories, steps, distance, timestamp, device_id, sync_id, time_index, source_command, raw_packet_hex) VALUES (40, 1200, 950, ?, ?, ?, 0, 67, '')",
        (now.isoformat(), device_id, sync_id),
    )
    db.connection.execute(
        "INSERT INTO sleep_sessions(device_id, sync_id, start_timestamp, end_timestamp, total_minutes, state, score, is_provisional, source_command, raw_json) VALUES (?, ?, ?, ?, 420, 'sleep', 80, 0, 39, '{}')",
        (
            device_id,
            sync_id,
            datetime(2026, 5, 28, 22, 0, tzinfo=UTC).isoformat(),
            datetime(2026, 5, 29, 5, 0, tzinfo=UTC).isoformat(),
        ),
    )
    sleep_session_id = int(db.connection.execute("SELECT sleep_session_id FROM sleep_sessions").fetchone()[0])
    db.connection.execute(
        "INSERT INTO sleep_stage_samples(sleep_session_id, device_id, sync_id, sequence_index, stage, start_timestamp, end_timestamp, minutes, is_provisional, raw_json) VALUES (?, ?, ?, 0, 'deep', ?, ?, 120, 0, '{}')",
        (
            sleep_session_id,
            device_id,
            sync_id,
            datetime(2026, 5, 28, 22, 0, tzinfo=UTC).isoformat(),
            datetime(2026, 5, 29, 0, 0, tzinfo=UTC).isoformat(),
        ),
    )
    db.connection.execute(
        "INSERT INTO blood_oxygen_samples(device_id, sync_id, timestamp, sample_index, min_percent, max_percent, interval_minutes, is_provisional, source_command, raw_packet_hex) VALUES (?, ?, ?, 0, 95, 98, 30, 0, 42, '')",
        (device_id, sync_id, now.isoformat()),
    )
    db.connection.execute(
        "INSERT INTO blood_pressure_readings(device_id, sync_id, timestamp, systolic, diastolic, source_command, raw_packet_hex) VALUES (?, ?, ?, 121, 79, 20, '')",
        (device_id, sync_id, now.isoformat()),
    )
    db.connection.execute(
        "INSERT INTO pressure_samples(device_id, sync_id, timestamp, sample_index, value, interval_minutes, source_command, raw_packet_hex) VALUES (?, ?, ?, 0, 36, 30, 55, '')",
        (device_id, sync_id, now.isoformat()),
    )
    db.connection.execute(
        "INSERT INTO hrv_samples(device_id, sync_id, timestamp, sample_index, value, interval_minutes, source_command, raw_packet_hex) VALUES (?, ?, ?, 0, 48, 30, 57, '')",
        (device_id, sync_id, now.isoformat()),
    )
    db.connection.commit()
    db.close()


def test_dashboard_api_today_and_health(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "h59.sqlite"
    _seed_db(db_path)
    monkeypatch.setattr(today_payload_module, "utc_now", lambda: datetime(2026, 5, 29, 12, 0, tzinfo=UTC))
    app = create_app(
        Settings(
            db_path=db_path,
            read_only=False,
            host="127.0.0.1",
            port=8000,
            cors_origins=("http://localhost:5173",),
        )
    )
    client = TestClient(app)

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["time_context"]["storage_timezone"] == "UTC"
    assert health.json()["time_context"]["display_timezone"] == "browser-local"

    today = client.get("/api/today")
    assert today.status_code == 200
    payload = today.json()
    assert payload["time_context"]["query_day_boundary_timezone"] == "UTC"
    assert payload["device"]["battery_percent"] == 82
    card_ids = {card["id"] for card in payload["cards"]}
    assert {"steps", "heart_rate", "sleep", "spo2", "hrv", "stress", "blood_pressure"}.issubset(card_ids)
    bp_card = next(card for card in payload["cards"] if card["id"] == "blood_pressure")
    assert bp_card["display_value"] == "121/79 mmHg"


def test_dashboard_api_metric_and_quality(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "h59.sqlite"
    _seed_db(db_path)
    monkeypatch.setattr(metrics_payload_module, "range_start", lambda _range_name: datetime(2026, 5, 28, 12, 0, tzinfo=UTC))
    app = create_app(
        Settings(
            db_path=db_path,
            read_only=False,
            host="127.0.0.1",
            port=8000,
            cors_origins=("http://localhost:5173",),
        )
    )
    client = TestClient(app)

    metric = client.get("/api/metrics/heart-rate?range=24h")
    assert metric.status_code == 200
    assert metric.json()["available"] is True

    quality = client.get("/api/data-quality")
    assert quality.status_code == 200
    assert quality.json()["sample_counts_today"]["heart_rate"] >= 1


def test_dashboard_api_metric_filters_future_points(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "h59.sqlite"
    _seed_db(db_path)
    db = H59Database(db_path)
    try:
        device_id = int(db.connection.execute("SELECT device_id FROM devices LIMIT 1").fetchone()[0])
        sync_id = int(db.connection.execute("SELECT MIN(sync_id) FROM syncs").fetchone()[0])
        db.connection.execute("DELETE FROM blood_oxygen_samples")
        db.connection.executemany(
            "INSERT INTO blood_oxygen_samples(device_id, sync_id, timestamp, sample_index, min_percent, max_percent, interval_minutes, is_provisional, source_command, raw_packet_hex) VALUES (?, ?, ?, ?, ?, ?, 30, 0, 42, '')",
            [
                (device_id, sync_id, "2026-05-29T11:30:00+00:00", 0, 95, 97),
                (device_id, sync_id, "2026-05-29T12:30:00+00:00", 1, 96, 98),
            ],
        )
        db.connection.commit()
    finally:
        db.close()

    monkeypatch.setattr(metrics_payload_module, "range_start", lambda _range_name: datetime(2026, 5, 28, 12, 0, tzinfo=UTC))
    monkeypatch.setattr(metrics_payload_module, "utc_now", lambda: datetime(2026, 5, 29, 12, 0, tzinfo=UTC))
    app = create_app(
        Settings(
            db_path=db_path,
            read_only=False,
            host="127.0.0.1",
            port=8000,
            cors_origins=("http://localhost:5173",),
        )
    )
    client = TestClient(app)

    metric = client.get("/api/metrics/spo2?range=24h")
    assert metric.status_code == 200
    payload = metric.json()
    assert [point["timestamp"] for point in payload["points"]] == ["2026-05-29T11:30:00+00:00"]


def test_dashboard_api_today_does_not_fall_back_to_prior_activity_day(tmp_path: Path) -> None:
    db_path = tmp_path / "h59.sqlite"
    _seed_db(db_path)
    db = H59Database(db_path)
    try:
        db.connection.execute("DELETE FROM sport_details")
        device_id = int(db.connection.execute("SELECT device_id FROM devices LIMIT 1").fetchone()[0])
        sync_id = int(db.connection.execute("SELECT MIN(sync_id) FROM syncs").fetchone()[0])
        db.connection.execute(
            "INSERT INTO sport_details(calories, steps, distance, timestamp, device_id, sync_id, time_index, source_command, raw_packet_hex) VALUES (40, 1200, 950, ?, ?, ?, 0, 67, '')",
            (datetime(2026, 5, 28, 11, 0, tzinfo=UTC).isoformat(), device_id, sync_id),
        )
        db.connection.commit()
    finally:
        db.close()

    app = create_app(
        Settings(
            db_path=db_path,
            read_only=False,
            host="127.0.0.1",
            port=8000,
            cors_origins=("http://localhost:5173",),
        )
    )
    client = TestClient(app)

    today = client.get("/api/today")
    assert today.status_code == 200
    payload = today.json()
    steps_card = next(card for card in payload["cards"] if card["id"] == "steps")
    assert steps_card["value"] is None
    assert steps_card["status"] == "empty"
    assert steps_card["subtitle"] == "No activity summaries"


def test_dashboard_api_today_uses_utc_day_boundaries(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "h59.sqlite"
    _seed_db(db_path)
    db = H59Database(db_path)
    try:
        device_id = int(db.connection.execute("SELECT device_id FROM devices LIMIT 1").fetchone()[0])
        sync_id = int(db.connection.execute("SELECT MIN(sync_id) FROM syncs").fetchone()[0])
        db.connection.execute("DELETE FROM heart_rates")
        db.connection.executemany(
            "INSERT INTO heart_rates(reading, timestamp, device_id, sync_id, source_command, raw_packet_hex) VALUES (?, ?, ?, ?, 21, '')",
            [
                (61, "2026-05-28T23:55:00+00:00", device_id, sync_id),
                (72, "2026-05-29T00:05:00+00:00", device_id, sync_id),
            ],
        )
        db.connection.commit()
    finally:
        db.close()

    monkeypatch.setattr(today_payload_module, "utc_now", lambda: datetime(2026, 5, 29, 12, 0, tzinfo=UTC))

    app = create_app(
        Settings(
            db_path=db_path,
            read_only=False,
            host="127.0.0.1",
            port=8000,
            cors_origins=("http://localhost:5173",),
        )
    )
    client = TestClient(app)

    today = client.get("/api/today")
    assert today.status_code == 200
    payload = today.json()
    heart_card = next(card for card in payload["cards"] if card["id"] == "heart_rate")
    assert heart_card["value"] == 72
    assert len(heart_card["sparkline"]) == 1
    assert heart_card["sparkline"][0]["timestamp"] == "2026-05-29T00:05:00+00:00"


def test_dashboard_api_today_uses_realtime_health_check_for_blood_pressure(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "h59.sqlite"
    _seed_db(db_path)
    db = H59Database(db_path)
    try:
        device_id = int(db.connection.execute("SELECT device_id FROM devices LIMIT 1").fetchone()[0])
        sync_id = int(db.connection.execute("SELECT MIN(sync_id) FROM syncs").fetchone()[0])
        db.connection.execute("DELETE FROM blood_pressure_readings")
        db.record_realtime_observations(
            device_id,
            sync_id,
            observations=[
                RealtimeObservation(
                    metric_code="health-check.diastolic",
                    timestamp=datetime(2026, 5, 29, 12, 0, tzinfo=UTC),
                    value_numeric=79,
                    raw_packet_hex="6905004f793f00000000000000000000",
                    source_command=105,
                ),
                RealtimeObservation(
                    metric_code="health-check.systolic",
                    timestamp=datetime(2026, 5, 29, 12, 0, tzinfo=UTC),
                    value_numeric=121,
                    raw_packet_hex="6905004f793f00000000000000000000",
                    source_command=105,
                ),
            ],
        )
        db.connection.commit()
    finally:
        db.close()

    monkeypatch.setattr(today_payload_module, "utc_now", lambda: datetime(2026, 5, 29, 12, 0, tzinfo=UTC))
    app = create_app(
        Settings(
            db_path=db_path,
            read_only=False,
            host="127.0.0.1",
            port=8000,
            cors_origins=("http://localhost:5173",),
        )
    )
    client = TestClient(app)

    today = client.get("/api/today")
    assert today.status_code == 200
    payload = today.json()
    bp_card = next(card for card in payload["cards"] if card["id"] == "blood_pressure")
    assert bp_card["display_value"] == "121/79 mmHg"



def test_insights_current_endpoint_scores_from_python_module_over_database_views(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "h59.sqlite"
    _seed_db(db_path)
    db = H59Database(db_path)
    try:
        device_id = int(db.connection.execute("SELECT device_id FROM devices LIMIT 1").fetchone()[0])
        sync_id = int(db.connection.execute("SELECT MIN(sync_id) FROM syncs").fetchone()[0])
        db.upsert_device(
            address="66:77:88:99:AA:BB",
            name="H59_OTHER",
            advertisement=None,
            hw_version=None,
            fw_version=None,
            last_seen_at="2026-05-30T08:00:00+00:00",
        )
        db.connection.execute("DELETE FROM heart_rates")
        db.connection.execute("DELETE FROM hrv_samples")
        db.connection.execute("DELETE FROM sport_details")
        rows = [
            ("2026-05-26", 50, 60, 5000),
            ("2026-05-27", 50, 60, 5000),
            ("2026-05-28", 50, 60, 5000),
            ("2026-05-29", 35, 70, 9000),
        ]
        for index, (day, hrv, hr, steps) in enumerate(rows):
            db.connection.execute(
                "INSERT INTO hrv_samples(device_id, sync_id, timestamp, sample_index, value, interval_minutes, source_command, raw_packet_hex) VALUES (?, ?, ?, ?, ?, 30, 57, '')",
                (device_id, sync_id, f"{day}T06:00:00+00:00", index, hrv),
            )
            db.connection.execute(
                "INSERT INTO heart_rates(reading, timestamp, device_id, sync_id, source_command, raw_packet_hex) VALUES (?, ?, ?, ?, 21, '')",
                (hr, f"{day}T06:00:00+00:00", device_id, sync_id),
            )
            db.connection.execute(
                "INSERT INTO sport_details(calories, steps, distance, timestamp, device_id, sync_id, time_index, source_command, raw_packet_hex) VALUES (100, ?, 1000, ?, ?, ?, 0, 67, '')",
                (steps, f"{day}T12:00:00+00:00", device_id, sync_id),
            )
        fresh_sync_at = datetime.now(UTC).isoformat()
        next_sync_id = int(db.connection.execute("SELECT MAX(sync_id) + 1 FROM syncs").fetchone()[0])
        db.connection.execute(
            "INSERT INTO syncs(sync_id, comment, device_id, timestamp, finished_at, source) VALUES (?, ?, ?, ?, ?, ?)",
            (next_sync_id, None, device_id, fresh_sync_at, fresh_sync_at, "test"),
        )
        db.connection.commit()
    finally:
        db.close()

    app = create_app(
        Settings(
            db_path=db_path,
            read_only=False,
            host="127.0.0.1",
            port=8000,
            cors_origins=("http://localhost:5173",),
        )
    )
    client = TestClient(app)

    response = client.get(f"/api/insights/current?device={device_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["device"]["id"] == device_id
    assert payload["device"]["is_preferred"] is False
    assert payload["device"]["last_sync"] is not None
    assert payload["sync_context"]["latest_band_sync"] == payload["device"]["last_sync"]
    assert payload["sync_context"]["data_freshness"] == payload["device"]["data_freshness"]
    assert payload["sync_context"]["data_freshness"] == "fresh"
    assert payload["sync_context"]["is_stale"] is True
    assert payload["sync_context"]["data_as_of"] == payload["as_of"]
    assert "Always check sync_context.latest_band_sync" in " ".join(payload["llm_guardrails"])
    assert payload["state"] == "measurement_uncertain"
    assert payload["confidence"] == "low"
    assert "Latest health features are stale" in payload["sync_context"]["warning"]
    assert payload["readiness"]["score"] < 70
    assert payload["strain"]["score"] > 0
    assert payload["confidence"] in {"low", "medium", "high"}
    assert any("HRV" in factor for factor in payload["key_factors"])
    assert any("resting HR" in factor for factor in payload["key_factors"])
    assert "Do not diagnose" in " ".join(payload["llm_guardrails"])


def test_dashboard_api_creates_missing_health_views_when_opened_read_only(tmp_path: Path) -> None:
    db_path = tmp_path / "h59.sqlite"
    _seed_db(db_path)
    db = H59Database(db_path)
    try:
        db.connection.executescript(
            """
            DROP VIEW IF EXISTS health_metric_baselines;
            DROP VIEW IF EXISTS health_metric_observations;
            DROP VIEW IF EXISTS health_daily_features;
            """
        )
        db.connection.commit()
    finally:
        db.close()

    app = create_app(
        Settings(
            db_path=db_path,
            read_only=True,
            host="127.0.0.1",
            port=8000,
            cors_origins=("http://localhost:5173",),
        )
    )
    client = TestClient(app)

    response = client.get("/api/insights/current")
    assert response.status_code == 200

    db = H59Database(db_path)
    try:
        views = {
            row["name"]
            for row in db.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='view' AND name LIKE 'health_%'"
            ).fetchall()
        }
    finally:
        db.close()
    assert {"health_daily_features", "health_metric_observations", "health_metric_baselines"}.issubset(views)
