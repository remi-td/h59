import sqlite3
from datetime import UTC, datetime, timedelta, timezone

from h59_client.protocol import (
    ActivityBlock,
    BatteryStatus,
    BloodPressureReading,
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
from h59_client.storage import H59Database, RealtimeObservation, utc_text


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
    db.record_blood_pressure_readings(
        device_id,
        sync_id,
        readings=[
            BloodPressureReading(
                timestamp=datetime(2026, 5, 26, 9, 0, tzinfo=UTC),
                systolic=121,
                diastolic=79,
            )
        ],
        raw_packet_hex="14...",
        source_command=20,
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
    assert conn.execute("SELECT COUNT(*) FROM metric_codes").fetchone()[0] >= 1
    assert conn.execute("SELECT COUNT(*) FROM sport_details").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM heart_rates").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM realtime_samples").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM sleep_sessions").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM sleep_stage_samples").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM blood_oxygen_samples").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM blood_pressure_readings").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM pressure_samples").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM hrv_samples").fetchone()[0] == 2
    bp_row = conn.execute("SELECT systolic, diastolic FROM analytic_blood_pressure_intervals").fetchone()
    assert tuple(bp_row) == (121, 79)
    realtime_row = conn.execute(
        """
        SELECT mc.metric_code, rs.value_numeric, rs.source_command
        FROM realtime_samples AS rs
        JOIN metric_codes AS mc
          ON mc.metric_code_id = rs.metric_code_id
        LIMIT 1
        """
    ).fetchone()
    assert tuple(realtime_row) == ("spo2", 0.0, 105)
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


def test_storage_migrates_legacy_device_and_realtime_schema(tmp_path):
    db_path = tmp_path / "legacy.sqlite"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE devices (
            device_id INTEGER PRIMARY KEY,
            address TEXT NOT NULL UNIQUE,
            name TEXT,
            advertisement_json TEXT,
            hw_version TEXT,
            fw_version TEXT,
            last_seen_at TEXT
        );
        CREATE TABLE syncs (
            sync_id INTEGER PRIMARY KEY,
            comment TEXT,
            device_id INTEGER NOT NULL,
            timestamp TEXT NOT NULL,
            finished_at TEXT,
            source TEXT
        );
        CREATE TABLE realtime_samples (
            realtime_sample_id INTEGER PRIMARY KEY,
            device_id INTEGER NOT NULL,
            sync_id INTEGER NOT NULL,
            timestamp TEXT NOT NULL,
            metric TEXT NOT NULL,
            value INTEGER NOT NULL,
            error_code INTEGER NOT NULL DEFAULT 0,
            raw_packet_hex TEXT
        );
        """
    )
    conn.execute(
        """
        INSERT INTO devices(device_id, address, name, advertisement_json, hw_version, fw_version, last_seen_at)
        VALUES (1, 'AA-BB', 'H59_DEMO', NULL, NULL, NULL, '2026-05-25T19:00:00+00:00')
        """
    )
    conn.execute(
        """
        INSERT INTO syncs(sync_id, device_id, timestamp, source)
        VALUES (1, 1, '2026-05-25T19:00:00+00:00', 'test')
        """
    )
    conn.execute(
        """
        INSERT INTO realtime_samples(realtime_sample_id, device_id, sync_id, timestamp, metric, value, error_code, raw_packet_hex)
        VALUES (1, 1, 1, '2026-05-25T19:00:01+00:00', 'spo2', 97, 0, '690300...')
        """
    )
    conn.commit()
    conn.close()

    db = H59Database(db_path)
    columns = {row["name"] for row in db.connection.execute("PRAGMA table_info(devices)").fetchall()}
    assert "nickname" in columns
    realtime_columns = {row["name"] for row in db.connection.execute("PRAGMA table_info(realtime_samples)").fetchall()}
    assert {"metric_code_id", "value_numeric", "value_text", "source_command"} <= realtime_columns
    row = db.connection.execute(
        """
        SELECT rs.value_numeric, rs.source_command, mc.metric_code
        FROM realtime_samples AS rs
        JOIN metric_codes AS mc
          ON mc.metric_code_id = rs.metric_code_id
        WHERE rs.realtime_sample_id=1
        """
    ).fetchone()
    assert tuple(row) == (97.0, 105, "spo2")
    assert db.list_devices()[0]["address"] == "AA-BB"
    db.close()


def test_merge_history_imports_only_older_measurements_by_device_address(tmp_path):
    source_db = H59Database(tmp_path / "source.sqlite")
    source_device_id = source_db.upsert_device(
        address="AA-BB",
        name="H59_DEMO",
        advertisement=None,
        hw_version="H59_V2.2",
        fw_version="H59_FW",
        last_seen_at="2026-05-25T19:00:00+00:00",
    )
    source_sync_id = source_db.create_sync(source_device_id, started_at="2026-05-25T19:00:00+00:00", source="test")
    source_db.record_heart_rate_day(
        source_device_id,
        source_sync_id,
        day=HeartRateDay(
            heart_rates=[61, 62, 63],
            timestamp=datetime(2026, 5, 24, 0, 0, tzinfo=UTC),
            size=1,
            index=3,
            range=5,
        ),
        raw_packet_hex="15-source",
    )
    source_db.record_activity_blocks(
        source_device_id,
        source_sync_id,
        blocks=[
            ActivityBlock(year=2026, month=5, day=24, time_index=28, calories=100, steps=200, distance=300),
        ],
        raw_packet_hex="43-source",
    )
    source_db.record_sleep_sessions(
        source_device_id,
        source_sync_id,
        reference=datetime(2026, 5, 25, 12, 0, tzinfo=UTC),
        sessions=[
            SleepSession(
                days_ago=1,
                bytes_used=10,
                sleep_start_minutes=1380,
                sleep_end_minutes=360,
                periods=[SleepPeriod(stage="light", minutes=120), SleepPeriod(stage="deep", minutes=120)],
            )
        ],
        raw_packet_hex="bc27-source",
        source_command=39,
    )
    source_db.finish_sync(source_sync_id, finished_at="2026-05-25T19:05:00+00:00")
    source_db.close()

    target_db = H59Database(tmp_path / "target.sqlite")
    target_device_id = target_db.upsert_device(
        address="AA-BB",
        name="H59_DEMO",
        advertisement=None,
        hw_version="H59_V2.2",
        fw_version="H59_FW",
        last_seen_at="2026-05-26T19:00:00+00:00",
    )
    target_sync_id = target_db.create_sync(target_device_id, started_at="2026-05-26T19:00:00+00:00", source="test")
    target_db.record_heart_rate_day(
        target_device_id,
        target_sync_id,
        day=HeartRateDay(
            heart_rates=[71, 72],
            timestamp=datetime(2026, 5, 25, 0, 0, tzinfo=UTC),
            size=1,
            index=2,
            range=5,
        ),
        raw_packet_hex="15-target",
    )
    target_db.record_activity_blocks(
        target_device_id,
        target_sync_id,
        blocks=[
            ActivityBlock(year=2026, month=5, day=25, time_index=28, calories=110, steps=210, distance=310),
        ],
        raw_packet_hex="43-target",
    )
    target_db.record_sleep_sessions(
        target_device_id,
        target_sync_id,
        reference=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
        sessions=[
            SleepSession(
                days_ago=1,
                bytes_used=10,
                sleep_start_minutes=1380,
                sleep_end_minutes=360,
                periods=[SleepPeriod(stage="light", minutes=130), SleepPeriod(stage="deep", minutes=110)],
            )
        ],
        raw_packet_hex="bc27-target",
        source_command=39,
    )

    summary = target_db.merge_history_from(tmp_path / "source.sqlite")
    conn = target_db.connection
    assert summary["imported_rows"] > 0
    assert conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM heart_rates").fetchone()[0] == 5
    assert conn.execute("SELECT COUNT(*) FROM sport_details").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM sleep_sessions").fetchone()[0] == 2
    migration_sync = conn.execute(
        "SELECT sync_id, source FROM syncs WHERE device_id=? AND source='db.merge_history' ORDER BY sync_id DESC LIMIT 1",
        (target_device_id,),
    ).fetchone()
    assert migration_sync is not None
    assert conn.execute("SELECT MIN(timestamp) FROM heart_rates WHERE device_id=?", (target_device_id,)).fetchone()[0] == "2026-05-24T00:00:00+00:00"
    assert conn.execute("SELECT MIN(timestamp) FROM sport_details WHERE device_id=?", (target_device_id,)).fetchone()[0] == "2026-05-24T07:00:00+00:00"
    target_db.close()


def test_analytic_blood_pressure_intervals_include_realtime_health_check_rows(tmp_path):
    db = H59Database(tmp_path / "h59.sqlite")
    device_id = db.upsert_device(
        address="AA-BB",
        name="H59_DEMO",
        advertisement=None,
        hw_version=None,
        fw_version=None,
        last_seen_at="2026-05-31T08:00:00+00:00",
    )
    sync_id = db.create_sync(device_id, started_at="2026-05-31T08:00:00+00:00", source="test")
    observed_at = datetime(2026, 5, 31, 8, 5, tzinfo=UTC)
    db.record_realtime_observations(
        device_id,
        sync_id,
        observations=[
            RealtimeObservation(
                metric_code="health-check.diastolic",
                timestamp=observed_at,
                value_numeric=67,
                raw_packet_hex="690500436f48a9030000000000000014",
                source_command=105,
            ),
            RealtimeObservation(
                metric_code="health-check.systolic",
                timestamp=observed_at,
                value_numeric=111,
                raw_packet_hex="690500436f48a9030000000000000014",
                source_command=105,
            ),
            RealtimeObservation(
                metric_code="health-check.heart-rate",
                timestamp=observed_at,
                value_numeric=72,
                raw_packet_hex="690500436f48a9030000000000000014",
                source_command=105,
            ),
        ],
    )
    row = db.connection.execute(
        """
        SELECT systolic, diastolic
        FROM analytic_blood_pressure_intervals
        WHERE device_id=?
        ORDER BY valid_from DESC
        LIMIT 1
        """,
        (device_id,),
    ).fetchone()
    assert tuple(row) == (111, 67)
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


def test_storage_supports_unique_nicknames_and_selector_lookup(tmp_path):
    db = H59Database(tmp_path / "h59.sqlite")
    first_id = db.upsert_device(
        address="AA-BB",
        name="H59_ONE",
        advertisement=None,
        hw_version=None,
        fw_version=None,
        last_seen_at="2026-05-25T19:00:00+00:00",
    )
    second_id = db.upsert_device(
        address="CC-DD",
        name="H59_TWO",
        advertisement=None,
        hw_version=None,
        fw_version=None,
        last_seen_at="2026-05-25T20:00:00+00:00",
    )

    row = db.set_device_nickname(str(first_id), "left-wrist")
    assert row["nickname"] == "left-wrist"
    assert db.get_device_by_selector("left-wrist")["device_id"] == first_id
    assert db.get_device_by_selector("AA-BB")["device_id"] == first_id
    assert db.get_device_by_selector(str(second_id))["address"] == "CC-DD"

    try:
        db.set_device_nickname(str(second_id), "left-wrist")
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError("expected duplicate nickname to violate uniqueness")

    db.close()


def test_storage_skips_invalid_sleep_sessions(tmp_path):
    db = H59Database(tmp_path / "h59.sqlite")
    device_id = db.upsert_device(
        address="AA-BB",
        name="H59_DEMO",
        advertisement=None,
        hw_version=None,
        fw_version=None,
        last_seen_at="2026-05-25T19:00:00+00:00",
    )
    sync_id = db.create_sync(device_id, started_at="2026-05-25T19:00:00+00:00", source="test")

    db.record_sleep_sessions(
        device_id,
        sync_id,
        reference=datetime(2026, 5, 27, 12, 0, tzinfo=UTC),
        sessions=[
            SleepSession(days_ago=2, bytes_used=1, sleep_start_minutes=773, sleep_end_minutes=1538, periods=[]),
            SleepSession(
                days_ago=2,
                bytes_used=10,
                sleep_start_minutes=1380,
                sleep_end_minutes=360,
                periods=[SleepPeriod(stage="light", minutes=60)],
            ),
        ],
        raw_packet_hex="bc27...",
        source_command=39,
    )

    conn = db.connection
    assert conn.execute("SELECT COUNT(*) FROM sleep_sessions").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM sleep_stage_samples WHERE start_timestamp IS NULL OR end_timestamp IS NULL").fetchone()[0] == 0
    db.close()


def test_storage_updates_existing_sleep_session_by_bounds(tmp_path):
    db = H59Database(tmp_path / "h59.sqlite")
    device_id = db.upsert_device(
        address="AA-BB",
        name="H59_DEMO",
        advertisement=None,
        hw_version=None,
        fw_version=None,
        last_seen_at="2026-05-25T19:00:00+00:00",
    )
    sync_id_1 = db.create_sync(device_id, started_at="2026-05-26T10:00:00+00:00", source="test")
    sync_id_2 = db.create_sync(device_id, started_at="2026-05-27T10:00:00+00:00", source="test")

    reference = datetime(2026, 5, 27, 12, 0, tzinfo=UTC)
    bounds_session = SleepSession(
        days_ago=1,
        bytes_used=42,
        sleep_start_minutes=1434,
        sleep_end_minutes=413,
        periods=[SleepPeriod(stage="light", minutes=60), SleepPeriod(stage="deep", minutes=60)],
    )
    db.record_sleep_sessions(
        device_id,
        sync_id_1,
        reference=reference,
        sessions=[bounds_session],
        raw_packet_hex="bc27-old",
        source_command=39,
    )
    db.record_sleep_sessions(
        device_id,
        sync_id_2,
        reference=reference,
        sessions=[
            SleepSession(
                days_ago=1,
                bytes_used=42,
                sleep_start_minutes=1434,
                sleep_end_minutes=413,
                periods=[SleepPeriod(stage="light", minutes=70), SleepPeriod(stage="deep", minutes=70)],
            )
        ],
        raw_packet_hex="bc27-new",
        source_command=39,
    )

    conn = db.connection
    assert conn.execute("SELECT COUNT(*) FROM sleep_sessions").fetchone()[0] == 1
    assert conn.execute("SELECT total_minutes FROM sleep_sessions").fetchone()[0] == 140
    assert conn.execute("SELECT COUNT(*) FROM sleep_stage_samples").fetchone()[0] == 2
    db.close()


def test_storage_updates_existing_sleep_session_by_raw_json_identity(tmp_path):
    db = H59Database(tmp_path / "h59.sqlite")
    device_id = db.upsert_device(
        address="AA-BB",
        name="H59_DEMO",
        advertisement=None,
        hw_version=None,
        fw_version=None,
        last_seen_at="2026-05-31T10:00:00+00:00",
    )
    sync_id_1 = db.create_sync(device_id, started_at="2026-05-31T10:00:00+00:00", source="test")
    sync_id_2 = db.create_sync(device_id, started_at="2026-06-01T10:00:00+00:00", source="test")

    repeated_session = SleepSession(
        days_ago=0,
        bytes_used=6,
        sleep_start_minutes=1389,
        sleep_end_minutes=1401,
        periods=[SleepPeriod(stage="light", minutes=12)],
    )
    db.record_sleep_sessions(
        device_id,
        sync_id_1,
        reference=datetime(2026, 5, 31, 12, 0, tzinfo=UTC),
        sessions=[repeated_session],
        raw_packet_hex="bc27-first",
        source_command=39,
    )
    db.record_sleep_sessions(
        device_id,
        sync_id_2,
        reference=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
        sessions=[repeated_session],
        raw_packet_hex="bc27-second",
        source_command=39,
    )

    row = db.connection.execute(
        """
        SELECT sync_id, start_timestamp, end_timestamp, total_minutes
        FROM sleep_sessions
        """
    ).fetchone()
    assert db.connection.execute("SELECT COUNT(*) FROM sleep_sessions").fetchone()[0] == 1
    assert db.connection.execute("SELECT COUNT(*) FROM sleep_stage_samples").fetchone()[0] == 1
    assert int(row["sync_id"]) == sync_id_2
    assert row["start_timestamp"] == "2026-06-01T23:09:00+00:00"
    assert row["end_timestamp"] == "2026-06-01T23:21:00+00:00"
    assert int(row["total_minutes"]) == 12

    db.close()


def test_storage_normalizes_unknown_sleep_stage_to_rem(tmp_path):
    db = H59Database(tmp_path / "h59.sqlite")
    device_id = db.upsert_device(
        address="AA-BB",
        name="H59_DEMO",
        advertisement=None,
        hw_version=None,
        fw_version=None,
        last_seen_at="2026-05-27T10:00:00+00:00",
    )
    sync_id = db.create_sync(device_id, started_at="2026-05-27T10:00:00+00:00", source="test")

    db.record_sleep_sessions(
        device_id,
        sync_id,
        reference=datetime(2026, 5, 27, 12, 0, tzinfo=UTC),
        sessions=[
            SleepSession(
                days_ago=1,
                bytes_used=42,
                sleep_start_minutes=1434,
                sleep_end_minutes=413,
                periods=[SleepPeriod(stage="unknown-4", minutes=90), SleepPeriod(stage="deep", minutes=60)],
            )
        ],
        raw_packet_hex="bc27",
        source_command=39,
    )

    conn = db.connection
    row = conn.execute(
        "SELECT stage, is_provisional, raw_json FROM sleep_stage_samples ORDER BY sequence_index ASC LIMIT 1"
    ).fetchone()
    assert row["stage"] == "rem"
    assert row["is_provisional"] == 1
    assert "unknown-4" in row["raw_json"]
    assert conn.execute("SELECT is_provisional FROM sleep_sessions").fetchone()[0] == 1
    db.close()


def test_storage_limits_same_day_heart_rate_rewrites_to_one_overlap_period(tmp_path):
    db = H59Database(tmp_path / "h59.sqlite")
    device_id = db.upsert_device(
        address="AA-BB",
        name="H59_DEMO",
        advertisement=None,
        hw_version=None,
        fw_version=None,
        last_seen_at="2026-05-27T12:00:00+00:00",
    )
    sync_id_1 = db.create_sync(device_id, started_at="2026-05-27T12:00:00+00:00", source="test")
    sync_id_2 = db.create_sync(device_id, started_at="2026-05-27T12:05:00+00:00", source="test")

    db.record_heart_rate_day(
        device_id,
        sync_id_1,
        day=HeartRateDay(
            heart_rates=[60, 61, 62, 0],
            timestamp=datetime(2026, 5, 27, 0, 0, tzinfo=UTC),
            size=1,
            index=3,
            range=5,
        ),
        raw_packet_hex="first",
    )
    db.record_heart_rate_day(
        device_id,
        sync_id_2,
        day=HeartRateDay(
            heart_rates=[99, 61, 62, 63],
            timestamp=datetime(2026, 5, 27, 0, 0, tzinfo=UTC),
            size=1,
            index=4,
            range=5,
        ),
        raw_packet_hex="second",
    )

    rows = db.connection.execute(
        "SELECT timestamp, reading, sync_id FROM heart_rates ORDER BY timestamp"
    ).fetchall()
    assert [row["reading"] for row in rows] == [60, 61, 62, 63]
    assert [row["sync_id"] for row in rows] == [sync_id_1, sync_id_2, sync_id_2, sync_id_2]
    db.close()


def test_storage_limits_same_day_activity_rewrites_to_one_overlap_period(tmp_path):
    db = H59Database(tmp_path / "h59.sqlite")
    device_id = db.upsert_device(
        address="AA-BB",
        name="H59_DEMO",
        advertisement=None,
        hw_version=None,
        fw_version=None,
        last_seen_at="2026-05-27T12:00:00+00:00",
    )
    sync_id_1 = db.create_sync(device_id, started_at="2026-05-27T12:00:00+00:00", source="test")
    sync_id_2 = db.create_sync(device_id, started_at="2026-05-27T12:15:00+00:00", source="test")

    first_blocks = [
        ActivityBlock(year=2026, month=5, day=27, time_index=0, calories=10, steps=100, distance=50),
        ActivityBlock(year=2026, month=5, day=27, time_index=1, calories=11, steps=101, distance=51),
        ActivityBlock(year=2026, month=5, day=27, time_index=2, calories=12, steps=102, distance=52),
    ]
    second_blocks = [
        ActivityBlock(year=2026, month=5, day=27, time_index=0, calories=99, steps=999, distance=999),
        ActivityBlock(year=2026, month=5, day=27, time_index=1, calories=11, steps=101, distance=51),
        ActivityBlock(year=2026, month=5, day=27, time_index=2, calories=12, steps=102, distance=52),
        ActivityBlock(year=2026, month=5, day=27, time_index=3, calories=13, steps=103, distance=53),
    ]

    db.record_activity_blocks(device_id, sync_id_1, blocks=first_blocks, raw_packet_hex="first")
    db.record_activity_blocks(device_id, sync_id_2, blocks=second_blocks, raw_packet_hex="second")

    rows = db.connection.execute(
        "SELECT timestamp, steps, sync_id FROM sport_details ORDER BY timestamp"
    ).fetchall()
    assert [row["steps"] for row in rows] == [100, 101, 102, 103]
    assert [row["sync_id"] for row in rows] == [sync_id_1, sync_id_2, sync_id_2, sync_id_2]
    db.close()


def test_storage_exposes_analytic_views(tmp_path):
    db = H59Database(tmp_path / "h59.sqlite")
    device_id = db.upsert_device(
        address="AA-BB",
        name="H59_DEMO",
        advertisement=None,
        hw_version=None,
        fw_version=None,
        last_seen_at="2026-05-25T19:00:00+00:00",
    )
    sync_id = db.create_sync(device_id, started_at="2026-05-25T19:00:00+00:00", source="test")
    db.record_heart_rate_settings(
        device_id,
        sync_id,
        timestamp="2026-05-25T19:00:00+00:00",
        settings=HeartRateLogSettings(enabled=True, interval=5),
        raw_packet_hex="",
    )
    db.record_activity_blocks(
        device_id,
        sync_id,
        blocks=[ActivityBlock(year=2026, month=5, day=25, time_index=28, calories=10, steps=100, distance=50)],
        raw_packet_hex="",
    )
    db.record_heart_rate_day(
        device_id,
        sync_id,
        day=HeartRateDay(
            heart_rates=[62],
            timestamp=datetime(2026, 5, 25, 0, 0, tzinfo=UTC),
            size=1,
            index=0,
            range=5,
        ),
        raw_packet_hex="",
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
                periods=[SleepPeriod(stage="light", minutes=120)],
            )
        ],
        raw_packet_hex="",
        source_command=39,
    )

    heart_interval = db.connection.execute(
        "SELECT valid_from, valid_to, value FROM analytic_heart_rate_intervals WHERE device_id=? LIMIT 1",
        (device_id,),
    ).fetchone()
    activity_interval = db.connection.execute(
        "SELECT valid_from, valid_to, steps FROM analytic_activity_intervals WHERE device_id=? LIMIT 1",
        (device_id,),
    ).fetchone()
    sleep_interval = db.connection.execute(
        "SELECT valid_from, valid_to, stage FROM analytic_sleep_stage_intervals WHERE device_id=? LIMIT 1",
        (device_id,),
    ).fetchone()
    daily_steps = db.connection.execute(
        "SELECT steps_total FROM analytic_daily_steps WHERE device_id=? LIMIT 1",
        (device_id,),
    ).fetchone()

    assert heart_interval is not None
    assert heart_interval["valid_to"].endswith("+00:00")
    assert activity_interval is not None
    assert int(activity_interval["steps"]) == 100
    assert sleep_interval is not None
    assert sleep_interval["stage"] == "light"
    assert daily_steps is not None
    assert int(daily_steps["steps_total"]) == 100

    db.close()


def test_storage_dedupes_overlapping_sleep_sessions_in_canonical_view(tmp_path):
    db = H59Database(tmp_path / "h59.sqlite")
    device_id = db.upsert_device(
        address="AA-BB",
        name="H59_DEMO",
        advertisement=None,
        hw_version=None,
        fw_version=None,
        last_seen_at="2026-05-29T09:00:00+00:00",
    )
    sync_id = db.create_sync(device_id, started_at="2026-05-29T09:00:00+00:00", source="test")
    db.connection.execute(
        """
        INSERT INTO sleep_sessions(device_id, sync_id, start_timestamp, end_timestamp, total_minutes, state, score, is_provisional, source_command, raw_json)
        VALUES (?, ?, ?, ?, ?, 'decoded', NULL, 1, 39, '{\"source\":\"a\"}')
        """,
        (device_id, sync_id, "2026-05-28T23:41:00+00:00", "2026-05-29T07:50:00+00:00", 489),
    )
    session_a = int(db.connection.execute("SELECT last_insert_rowid()").fetchone()[0])
    db.connection.execute(
        """
        INSERT INTO sleep_stage_samples(sleep_session_id, device_id, sync_id, sequence_index, stage, start_timestamp, end_timestamp, minutes, is_provisional, raw_json)
        VALUES (?, ?, ?, 0, 'light', '2026-05-28T23:41:00+00:00', '2026-05-29T07:50:00+00:00', 489, 1, '{\"source\":\"a\"}')
        """,
        (session_a, device_id, sync_id),
    )
    db.connection.execute(
        """
        INSERT INTO sleep_sessions(device_id, sync_id, start_timestamp, end_timestamp, total_minutes, state, score, is_provisional, source_command, raw_json)
        VALUES (?, ?, ?, ?, ?, 'decoded', NULL, 1, 39, '{\"source\":\"b\"}')
        """,
        (device_id, sync_id, "2026-05-28T21:55:00+00:00", "2026-05-29T07:49:00+00:00", 594),
    )
    session_b = int(db.connection.execute("SELECT last_insert_rowid()").fetchone()[0])
    db.connection.execute(
        """
        INSERT INTO sleep_stage_samples(sleep_session_id, device_id, sync_id, sequence_index, stage, start_timestamp, end_timestamp, minutes, is_provisional, raw_json)
        VALUES (?, ?, ?, 0, 'no-data', '2026-05-28T21:55:00+00:00', '2026-05-29T01:54:00+00:00', 119, 1, '{\"source\":\"b\",\"segment\":0}')
        """,
        (session_b, device_id, sync_id),
    )
    db.connection.execute(
        """
        INSERT INTO sleep_stage_samples(sleep_session_id, device_id, sync_id, sequence_index, stage, start_timestamp, end_timestamp, minutes, is_provisional, raw_json)
        VALUES (?, ?, ?, 1, 'light', '2026-05-29T01:54:00+00:00', '2026-05-29T07:49:00+00:00', 475, 1, '{\"source\":\"b\",\"segment\":1}')
        """,
        (session_b, device_id, sync_id),
    )
    db.connection.commit()

    row = db.connection.execute(
        """
        SELECT sleep_session_id, total_minutes, no_data_minutes
        FROM analytic_sleep_sessions_canonical
        WHERE device_id=? AND sleep_day='2026-05-29'
        """,
        (device_id,),
    ).fetchone()
    daily_row = db.connection.execute(
        """
        SELECT minutes_total, session_count
        FROM analytic_daily_sleep
        WHERE device_id=? AND sleep_day='2026-05-29'
        """,
        (device_id,),
    ).fetchone()

    assert row is not None
    assert int(row["sleep_session_id"]) == session_a
    assert int(row["total_minutes"]) == 489
    assert int(row["no_data_minutes"]) == 0
    assert daily_row is not None
    assert int(daily_row["minutes_total"]) == 489
    assert int(daily_row["session_count"]) == 1

    db.close()


def test_storage_classifies_sleep_naps_and_excludes_them_from_canonical_view(tmp_path):
    db = H59Database(tmp_path / "h59.sqlite")
    device_id = db.upsert_device(
        address="AA-BB",
        name="H59_DEMO",
        advertisement=None,
        hw_version=None,
        fw_version=None,
        last_seen_at="2026-05-30T08:00:00+00:00",
    )
    sync_id = db.create_sync(device_id, started_at="2026-05-30T08:00:00+00:00", source="test")
    db.connection.execute(
        """
        INSERT INTO sleep_sessions(device_id, sync_id, start_timestamp, end_timestamp, total_minutes, state, score, is_provisional, source_command, raw_json)
        VALUES (?, ?, ?, ?, ?, 'decoded', NULL, 1, 39, '{\"source\":\"overnight\"}')
        """,
        (device_id, sync_id, "2026-05-29T21:55:00+00:00", "2026-05-30T07:49:00+00:00", 594),
    )
    overnight_session_id = int(db.connection.execute("SELECT last_insert_rowid()").fetchone()[0])
    db.connection.execute(
        """
        INSERT INTO sleep_stage_samples(sleep_session_id, device_id, sync_id, sequence_index, stage, start_timestamp, end_timestamp, minutes, is_provisional, raw_json)
        VALUES (?, ?, ?, 0, 'light', '2026-05-29T21:55:00+00:00', '2026-05-30T07:49:00+00:00', 594, 1, '{\"source\":\"overnight\"}')
        """,
        (overnight_session_id, device_id, sync_id),
    )
    db.connection.execute(
        """
        INSERT INTO sleep_sessions(device_id, sync_id, start_timestamp, end_timestamp, total_minutes, state, score, is_provisional, source_command, raw_json)
        VALUES (?, ?, ?, ?, ?, 'decoded', NULL, 0, 39, '{\"source\":\"nap\"}')
        """,
        (device_id, sync_id, "2026-05-30T01:39:00+00:00", "2026-05-30T01:53:00+00:00", 14),
    )
    nap_session_id = int(db.connection.execute("SELECT last_insert_rowid()").fetchone()[0])
    db.connection.execute(
        """
        INSERT INTO sleep_stage_samples(sleep_session_id, device_id, sync_id, sequence_index, stage, start_timestamp, end_timestamp, minutes, is_provisional, raw_json)
        VALUES (?, ?, ?, 0, 'light', '2026-05-30T01:39:00+00:00', '2026-05-30T01:53:00+00:00', 14, 0, '{\"source\":\"nap\"}')
        """,
        (nap_session_id, device_id, sync_id),
    )
    db.connection.commit()

    classified_rows = db.connection.execute(
        """
        SELECT sleep_session_id, session_kind, effective_minutes
        FROM analytic_sleep_sessions_classified
        WHERE device_id=?
        ORDER BY sleep_session_id ASC
        """,
        (device_id,),
    ).fetchall()
    canonical_row = db.connection.execute(
        """
        SELECT sleep_session_id, session_kind, total_minutes
        FROM analytic_sleep_sessions_canonical
        WHERE device_id=? AND sleep_day='2026-05-30'
        """,
        (device_id,),
    ).fetchone()

    assert [(int(row["sleep_session_id"]), row["session_kind"]) for row in classified_rows] == [
        (overnight_session_id, "overnight"),
        (nap_session_id, "nap"),
    ]
    assert int(classified_rows[0]["effective_minutes"]) == 594
    assert int(classified_rows[1]["effective_minutes"]) == 14
    assert canonical_row is not None
    assert int(canonical_row["sleep_session_id"]) == overnight_session_id
    assert canonical_row["session_kind"] == "overnight"
    assert int(canonical_row["total_minutes"]) == 594

    db.close()
