from datetime import UTC, datetime

from h59_client.report import render_health_dashboard_report
from h59_client.protocol import ActivityBlock, BatteryStatus, BloodOxygenHistory, BloodOxygenSample, HeartRateDay, HrvHistory, PressureHistory
from h59_client.storage import H59Database


def test_render_dashboard_report_surfaces_available_and_missing_metrics(tmp_path):
    db = H59Database(tmp_path / "h59.sqlite")
    device_id = db.upsert_device(
        address="AA-BB",
        name="H59_DEMO",
        advertisement={"local_name": "H59_DEMO"},
        hw_version="H59_V2.2",
        fw_version="H59_2.20.02_260319",
        last_seen_at="2026-05-26T15:00:00+00:00",
    )
    sync_id = db.create_sync(device_id, started_at="2026-05-26T15:00:00+00:00", source="test")
    db.record_battery(
        device_id,
        sync_id,
        timestamp="2026-05-26T15:00:01+00:00",
        sample=BatteryStatus(battery_level=85, charging=False),
        raw_packet_hex="03...",
    )
    db.record_capabilities(
        device_id,
        sync_id,
        timestamp="2026-05-26T15:00:02+00:00",
        capabilities={
            "support_spo2": True,
            "support_hrv": True,
            "support_pressure": True,
            "support_blood_pressure": True,
            "support_one_key_check": True,
        },
        raw_packet_hex="01...",
    )
    db.record_activity_blocks(
        device_id,
        sync_id,
        blocks=[
            ActivityBlock(year=2026, month=5, day=26, time_index=28, calories=100, steps=120, distance=80),
            ActivityBlock(year=2026, month=5, day=26, time_index=29, calories=120, steps=140, distance=90),
        ],
        raw_packet_hex="43...",
    )
    db.record_heart_rate_day(
        device_id,
        sync_id,
        day=HeartRateDay(
            heart_rates=[62, 63, 64, 0],
            timestamp=datetime(2026, 5, 26, 0, 0, tzinfo=UTC),
            size=1,
            index=2,
            range=5,
        ),
        raw_packet_hex="15...",
    )
    db.record_blood_oxygen_history(
        device_id,
        sync_id,
        target=datetime(2026, 5, 26, 0, 0, tzinfo=UTC),
        history=BloodOxygenHistory(
            unknown_flag=1,
            samples=[
                BloodOxygenSample(min_percent=97, max_percent=99),
                BloodOxygenSample(min_percent=98, max_percent=99),
            ],
        ),
        raw_packet_hex="bc2a...",
        source_command=42,
    )
    db.record_pressure_history(
        device_id,
        sync_id,
        target=datetime(2026, 5, 26, 0, 0, tzinfo=UTC),
        history=PressureHistory(values=[43, 41, 0], range_minutes=30),
        raw_packet_hex="37...",
        source_command=55,
    )
    db.record_hrv_history(
        device_id,
        sync_id,
        target=datetime(2026, 5, 26, 0, 0, tzinfo=UTC),
        history=HrvHistory(values=[47, 44, 0], range_minutes=30),
        raw_packet_hex="39...",
        source_command=57,
    )
    db.finish_sync(sync_id, finished_at="2026-05-26T15:00:03+00:00")

    markdown = render_health_dashboard_report(tmp_path / "h59.sqlite", report_date="2026-05-26")

    assert "# H59 Health Dashboard Data Audit" in markdown
    assert "| Steps | Available | Partial: Daily totals and hourly buckets from 15-minute activity bins |" in markdown
    assert "| Heart rate | Available | Available: Latest/min/max/avg from historical 5-minute samples |" in markdown
    assert "| Sleep | Missing | Missing: No decoded sleep sessions in current database |" in markdown
    assert "### Blood Oxygen / SpO2" in markdown
    assert "- Historical samples: `2` total, `2` on selected day" in markdown
    assert "### HRV" in markdown
    assert "### Stress / Pressure-like" in markdown
    assert "### Blood Pressure" in markdown
    assert "- Not available in the current database." in markdown
    assert "These sessions are inferred from contiguous 15-minute activity bins" in markdown

    db.close()


def test_render_dashboard_report_flags_incomplete_syncs(tmp_path):
    db = H59Database(tmp_path / "h59.sqlite")
    device_id = db.upsert_device(
        address="AA-BB",
        name="H59_DEMO",
        advertisement=None,
        hw_version=None,
        fw_version=None,
        last_seen_at="2026-05-26T15:00:00+00:00",
    )
    db.create_sync(device_id, started_at="2026-05-26T15:00:00+00:00", source="test")

    markdown = render_health_dashboard_report(tmp_path / "h59.sqlite", report_date="2026-05-26")

    assert "Warning: at least one sync session in the database has no `finished_at`" in markdown

    db.close()
