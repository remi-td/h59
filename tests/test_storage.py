from datetime import UTC, datetime, timedelta, timezone

from h59_client.protocol import (
    ActivityBlock,
    BatteryStatus,
    BloodOxygenHistory,
    BloodOxygenSample,
    HeartRateDay,
    HeartRateLogSettings,
    HrvHistory,
    PressureHistory,
    RealTimeSample,
    SleepPeriod,
    SleepSession,
)
from h59_client.storage import H59Database, utc_text


def test_storage_records_raw_and_decoded_data(tmp_path):
    db = H59Database(tmp_path / "h59.sqlite")
    device_id = db.upsert_device(
        address="AA-BB",
        name="H59_DEMO",
        advertisement={"local_name": "H59_DEMO"},
        hw_version="H59_V2.2",
        fw_version="H59_2.20.02_260319",
        last_seen_at="2026-05-25T21:00:00+02:00",
    )
    sync_id = db.create_sync(device_id, started_at="2026-05-25T21:00:00+02:00", source="test")

    db.record_gatt_snapshot(
        device_id,
        sync_id,
        observed_at="2026-05-25T19:00:01+00:00",
        services=[
            {
                "uuid": "svc",
                "description": "Service",
                "chars": [
                    {
                        "uuid": "char",
                        "handle": 1,
                        "properties": ["read"],
                        "read_value_hex": "01",
                        "read_value_text": "\u0001",
                    }
                ],
            }
        ],
    )
    db.record_raw_packet(
        device_id,
        sync_id,
        timestamp="2026-05-25T19:00:02+00:00",
        direction="rx",
        channel_uuid="6e400003",
        packet_hex="0357000000000000000000000000005a",
        command_id=3,
    )
    db.record_battery(
        device_id,
        sync_id,
        timestamp="2026-05-25T19:00:03+00:00",
        sample=BatteryStatus(battery_level=87, charging=False),
        raw_packet_hex="0357000000000000000000000000005a",
    )
    db.record_heart_rate_settings(
        device_id,
        sync_id,
        timestamp="2026-05-25T19:00:04+00:00",
        settings=HeartRateLogSettings(enabled=True, interval=5),
        raw_packet_hex="16010105050000000000000000000022",
    )
    db.record_capabilities(
        device_id,
        sync_id,
        timestamp="2026-05-25T19:00:05+00:00",
        capabilities={"support_spo2": True},
        raw_packet_hex="01000001160000000001002000003069",
    )
    db.record_activity_blocks(
        device_id,
        sync_id,
        blocks=[
            ActivityBlock(year=2026, month=5, day=25, time_index=28, calories=6310, steps=237, distance=146),
        ],
        raw_packet_hex="43...",
    )
    db.record_heart_rate_day(
        device_id,
        sync_id,
        day=HeartRateDay(
            heart_rates=[62, 63, 0],
            timestamp=datetime(2026, 5, 25, 0, 0, tzinfo=UTC),
            size=1,
            index=2,
            range=5,
        ),
        raw_packet_hex="15...",
    )
    db.record_realtime_samples(
        device_id,
        sync_id,
        observed_at="2026-05-25T19:00:06+00:00",
        samples=[(RealTimeSample(metric="spo2", value=0, error_code=0), "690300...")],
    )
    db.record_sleep_sessions(
        device_id,
        sync_id,
        reference=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
        sessions=[
            SleepSession(
                days_ago=1,
                bytes_used=10,
                sleep_start_minutes=1380,
                sleep_end_minutes=360,
                periods=[SleepPeriod(stage="light", minutes=120), SleepPeriod(stage="deep", minutes=120)],
            )
        ],
        raw_packet_hex="bc27...",
        source_command=39,
    )
    db.record_blood_oxygen_history(
        device_id,
        sync_id,
        target=datetime(2026, 5, 26, 0, 0, tzinfo=UTC),
        history=BloodOxygenHistory(
            unknown_flag=1,
            samples=[
                BloodOxygenSample(min_percent=97, max_percent=99),
                BloodOxygenSample(min_percent=0, max_percent=0),
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
    db.finish_sync(sync_id, finished_at="2026-05-25T19:00:07+00:00")

    conn = db.connection
    assert conn.execute("SELECT value FROM database_metadata WHERE key='timestamp_timezone'").fetchone()[0] == "UTC"
    assert conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM syncs").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM gatt_characteristics").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM gatt_reads").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM raw_packets").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM battery_samples").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM heart_rate_settings").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM capability_snapshots").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM sport_details").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM heart_rates").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM realtime_samples").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM sleep_sessions").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM sleep_stage_samples").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM blood_oxygen_samples").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM pressure_samples").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM hrv_samples").fetchone()[0] == 2
    assert conn.execute("SELECT last_seen_at FROM devices WHERE device_id=?", (device_id,)).fetchone()[0] == "2026-05-25T19:00:00+00:00"

    db.close()


def test_storage_returns_latest_sync_timestamp(tmp_path):
    db = H59Database(tmp_path / "h59.sqlite")
    device_id = db.upsert_device(
        address="AA-BB",
        name="H59_DEMO",
        advertisement=None,
        hw_version=None,
        fw_version=None,
        last_seen_at="2026-05-25T19:00:00+00:00",
    )
    db.create_sync(device_id, started_at="2026-05-25T19:00:00+00:00", source="test")
    db.create_sync(device_id, started_at="2026-05-26T06:00:00+00:00", source="test")

    latest = db.get_latest_sync_timestamp(device_id)
    assert latest == datetime.fromisoformat("2026-05-26T06:00:00+00:00")

    db.close()


def test_storage_allows_repeated_gatt_snapshots_for_same_device(tmp_path):
    db = H59Database(tmp_path / "h59.sqlite")
    device_id = db.upsert_device(
        address="AA-BB",
        name="H59_DEMO",
        advertisement=None,
        hw_version=None,
        fw_version=None,
        last_seen_at="2026-05-25T19:00:00+00:00",
    )
    sync_id_1 = db.create_sync(device_id, started_at="2026-05-25T19:00:00+00:00", source="test")
    sync_id_2 = db.create_sync(device_id, started_at="2026-05-25T20:00:00+00:00", source="test")
    services = [
        {
            "uuid": "svc",
            "description": "Service",
            "chars": [
                {
                    "uuid": "char",
                    "handle": 1,
                    "properties": ["read"],
                    "read_value_hex": "01",
                    "read_value_text": "\u0001",
                }
            ],
        }
    ]

    db.record_gatt_snapshot(device_id, sync_id_1, observed_at="2026-05-25T19:00:01+00:00", services=services)
    db.record_gatt_snapshot(device_id, sync_id_2, observed_at="2026-05-25T20:00:01+00:00", services=services)

    conn = db.connection
    assert conn.execute("SELECT COUNT(*) FROM gatt_characteristics").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM gatt_reads").fetchone()[0] == 2

    db.close()


def test_utc_text_normalizes_offsets_and_rejects_naive_values():
    assert utc_text("2026-05-26T17:00:00+02:00") == "2026-05-26T15:00:00+00:00"
    aware = datetime(2026, 5, 26, 17, 0, tzinfo=timezone(timedelta(hours=2)))
    assert utc_text(aware) == "2026-05-26T15:00:00+00:00"

    try:
        utc_text("2026-05-26T15:00:00")
    except ValueError:
        pass
    else:
        raise AssertionError("expected naive timestamp to be rejected")
