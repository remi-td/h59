"""SQLite storage for H59 raw and decoded sync data."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from h59_client.protocol import (
    ActivityBlock,
    BatteryStatus,
    BloodOxygenHistory,
    HeartRateDay,
    HeartRateLogSettings,
    HrvHistory,
    PressureHistory,
    RealTimeSample,
    SleepSession,
    to_json,
)


SCHEMA = """
CREATE TABLE IF NOT EXISTS database_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS devices (
    device_id INTEGER PRIMARY KEY,
    address TEXT NOT NULL UNIQUE,
    name TEXT,
    advertisement_json TEXT,
    hw_version TEXT,
    fw_version TEXT,
    last_seen_at TEXT,
    CHECK (last_seen_at IS NULL OR substr(last_seen_at, -6) = '+00:00')
);

CREATE TABLE IF NOT EXISTS syncs (
    sync_id INTEGER PRIMARY KEY,
    comment TEXT,
    device_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL CHECK (substr(timestamp, -6) = '+00:00'),
    finished_at TEXT CHECK (finished_at IS NULL OR substr(finished_at, -6) = '+00:00'),
    source TEXT,
    FOREIGN KEY(device_id) REFERENCES devices(device_id)
);

CREATE TABLE IF NOT EXISTS heart_rates (
    heart_rate_id INTEGER PRIMARY KEY,
    reading INTEGER NOT NULL,
    timestamp TEXT NOT NULL CHECK (substr(timestamp, -6) = '+00:00'),
    device_id INTEGER NOT NULL,
    sync_id INTEGER NOT NULL,
    source_command INTEGER,
    raw_packet_hex TEXT,
    UNIQUE(device_id, timestamp),
    FOREIGN KEY(device_id) REFERENCES devices(device_id),
    FOREIGN KEY(sync_id) REFERENCES syncs(sync_id)
);

CREATE TABLE IF NOT EXISTS sport_details (
    sport_detail_id INTEGER PRIMARY KEY,
    calories INTEGER NOT NULL,
    steps INTEGER NOT NULL,
    distance INTEGER NOT NULL,
    timestamp TEXT NOT NULL CHECK (substr(timestamp, -6) = '+00:00'),
    device_id INTEGER NOT NULL,
    sync_id INTEGER NOT NULL,
    time_index INTEGER,
    source_command INTEGER,
    raw_packet_hex TEXT,
    UNIQUE(device_id, timestamp),
    FOREIGN KEY(device_id) REFERENCES devices(device_id),
    FOREIGN KEY(sync_id) REFERENCES syncs(sync_id)
);

CREATE TABLE IF NOT EXISTS battery_samples (
    battery_sample_id INTEGER PRIMARY KEY,
    device_id INTEGER NOT NULL,
    sync_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL CHECK (substr(timestamp, -6) = '+00:00'),
    battery_level INTEGER NOT NULL,
    charging INTEGER NOT NULL,
    raw_packet_hex TEXT,
    FOREIGN KEY(device_id) REFERENCES devices(device_id),
    FOREIGN KEY(sync_id) REFERENCES syncs(sync_id)
);

CREATE TABLE IF NOT EXISTS heart_rate_settings (
    heart_rate_setting_id INTEGER PRIMARY KEY,
    device_id INTEGER NOT NULL,
    sync_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL CHECK (substr(timestamp, -6) = '+00:00'),
    enabled INTEGER NOT NULL,
    interval_minutes INTEGER NOT NULL,
    raw_packet_hex TEXT,
    FOREIGN KEY(device_id) REFERENCES devices(device_id),
    FOREIGN KEY(sync_id) REFERENCES syncs(sync_id)
);

CREATE TABLE IF NOT EXISTS capability_snapshots (
    capability_snapshot_id INTEGER PRIMARY KEY,
    device_id INTEGER NOT NULL,
    sync_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL CHECK (substr(timestamp, -6) = '+00:00'),
    raw_packet_hex TEXT,
    capabilities_json TEXT NOT NULL,
    FOREIGN KEY(device_id) REFERENCES devices(device_id),
    FOREIGN KEY(sync_id) REFERENCES syncs(sync_id)
);

CREATE TABLE IF NOT EXISTS realtime_samples (
    realtime_sample_id INTEGER PRIMARY KEY,
    device_id INTEGER NOT NULL,
    sync_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL CHECK (substr(timestamp, -6) = '+00:00'),
    metric TEXT NOT NULL,
    value INTEGER NOT NULL,
    error_code INTEGER NOT NULL DEFAULT 0,
    raw_packet_hex TEXT,
    FOREIGN KEY(device_id) REFERENCES devices(device_id),
    FOREIGN KEY(sync_id) REFERENCES syncs(sync_id)
);

CREATE TABLE IF NOT EXISTS gatt_characteristics (
    characteristic_id INTEGER PRIMARY KEY,
    device_id INTEGER NOT NULL,
    service_uuid TEXT NOT NULL,
    char_uuid TEXT NOT NULL,
    handle INTEGER,
    description TEXT,
    properties_json TEXT NOT NULL,
    UNIQUE(device_id, char_uuid, handle),
    FOREIGN KEY(device_id) REFERENCES devices(device_id)
);

CREATE TABLE IF NOT EXISTS gatt_reads (
    gatt_read_id INTEGER PRIMARY KEY,
    characteristic_id INTEGER NOT NULL,
    sync_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL CHECK (substr(timestamp, -6) = '+00:00'),
    value_hex TEXT,
    value_text TEXT,
    read_error TEXT,
    FOREIGN KEY(characteristic_id) REFERENCES gatt_characteristics(characteristic_id),
    FOREIGN KEY(sync_id) REFERENCES syncs(sync_id)
);

CREATE TABLE IF NOT EXISTS raw_packets (
    packet_id INTEGER PRIMARY KEY,
    device_id INTEGER NOT NULL,
    sync_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL CHECK (substr(timestamp, -6) = '+00:00'),
    direction TEXT NOT NULL,
    channel_uuid TEXT NOT NULL,
    command_id INTEGER,
    packet_hex TEXT NOT NULL,
    FOREIGN KEY(device_id) REFERENCES devices(device_id),
    FOREIGN KEY(sync_id) REFERENCES syncs(sync_id)
);

CREATE TABLE IF NOT EXISTS sleep_sessions (
    sleep_session_id INTEGER PRIMARY KEY,
    device_id INTEGER NOT NULL,
    sync_id INTEGER NOT NULL,
    start_timestamp TEXT CHECK (start_timestamp IS NULL OR substr(start_timestamp, -6) = '+00:00'),
    end_timestamp TEXT CHECK (end_timestamp IS NULL OR substr(end_timestamp, -6) = '+00:00'),
    total_minutes INTEGER,
    state TEXT,
    score REAL,
    is_provisional INTEGER NOT NULL DEFAULT 1,
    source_command INTEGER,
    raw_json TEXT NOT NULL,
    UNIQUE(device_id, source_command, raw_json),
    FOREIGN KEY(device_id) REFERENCES devices(device_id),
    FOREIGN KEY(sync_id) REFERENCES syncs(sync_id)
);

CREATE TABLE IF NOT EXISTS sleep_stage_samples (
    sleep_stage_sample_id INTEGER PRIMARY KEY,
    sleep_session_id INTEGER NOT NULL,
    device_id INTEGER NOT NULL,
    sync_id INTEGER NOT NULL,
    sequence_index INTEGER NOT NULL,
    stage TEXT NOT NULL,
    start_timestamp TEXT CHECK (start_timestamp IS NULL OR substr(start_timestamp, -6) = '+00:00'),
    end_timestamp TEXT CHECK (end_timestamp IS NULL OR substr(end_timestamp, -6) = '+00:00'),
    minutes INTEGER NOT NULL,
    is_provisional INTEGER NOT NULL DEFAULT 1,
    raw_json TEXT NOT NULL,
    UNIQUE(sleep_session_id, sequence_index),
    FOREIGN KEY(sleep_session_id) REFERENCES sleep_sessions(sleep_session_id),
    FOREIGN KEY(device_id) REFERENCES devices(device_id),
    FOREIGN KEY(sync_id) REFERENCES syncs(sync_id)
);

CREATE TABLE IF NOT EXISTS blood_oxygen_samples (
    blood_oxygen_sample_id INTEGER PRIMARY KEY,
    device_id INTEGER NOT NULL,
    sync_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL CHECK (substr(timestamp, -6) = '+00:00'),
    sample_index INTEGER NOT NULL,
    min_percent INTEGER NOT NULL,
    max_percent INTEGER NOT NULL,
    interval_minutes INTEGER NOT NULL,
    is_provisional INTEGER NOT NULL DEFAULT 1,
    source_command INTEGER,
    raw_packet_hex TEXT,
    UNIQUE(device_id, timestamp, source_command),
    FOREIGN KEY(device_id) REFERENCES devices(device_id),
    FOREIGN KEY(sync_id) REFERENCES syncs(sync_id)
);

CREATE TABLE IF NOT EXISTS pressure_samples (
    pressure_sample_id INTEGER PRIMARY KEY,
    device_id INTEGER NOT NULL,
    sync_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL CHECK (substr(timestamp, -6) = '+00:00'),
    sample_index INTEGER NOT NULL,
    value INTEGER NOT NULL,
    interval_minutes INTEGER NOT NULL,
    source_command INTEGER,
    raw_packet_hex TEXT,
    UNIQUE(device_id, timestamp, source_command),
    FOREIGN KEY(device_id) REFERENCES devices(device_id),
    FOREIGN KEY(sync_id) REFERENCES syncs(sync_id)
);

CREATE TABLE IF NOT EXISTS hrv_samples (
    hrv_sample_id INTEGER PRIMARY KEY,
    device_id INTEGER NOT NULL,
    sync_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL CHECK (substr(timestamp, -6) = '+00:00'),
    sample_index INTEGER NOT NULL,
    value INTEGER NOT NULL,
    interval_minutes INTEGER NOT NULL,
    source_command INTEGER,
    raw_packet_hex TEXT,
    UNIQUE(device_id, timestamp, source_command),
    FOREIGN KEY(device_id) REFERENCES devices(device_id),
    FOREIGN KEY(sync_id) REFERENCES syncs(sync_id)
);
"""


def utc_text(value: str | datetime) -> str:
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
    else:
        dt = value
    if dt.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware and convertible to UTC")
    return dt.astimezone(UTC).isoformat()


class H59Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(SCHEMA)
        self._write_metadata_defaults()
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def _write_metadata_defaults(self) -> None:
        self.connection.executemany(
            """
            INSERT INTO database_metadata(key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            [
                ("timestamp_timezone", "UTC"),
                ("timestamp_storage", "ISO-8601 text with explicit +00:00 offset"),
            ],
        )

    def upsert_device(
        self,
        *,
        address: str,
        name: str | None,
        advertisement: dict[str, Any] | None,
        hw_version: str | None,
        fw_version: str | None,
        last_seen_at: str | datetime,
    ) -> int:
        advertisement_json = json.dumps(advertisement, sort_keys=True) if advertisement is not None else None
        self.connection.execute(
            """
            INSERT INTO devices(address, name, advertisement_json, hw_version, fw_version, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(address) DO UPDATE SET
                name=excluded.name,
                advertisement_json=excluded.advertisement_json,
                hw_version=COALESCE(excluded.hw_version, devices.hw_version),
                fw_version=COALESCE(excluded.fw_version, devices.fw_version),
                last_seen_at=excluded.last_seen_at
            """,
            (address, name, advertisement_json, hw_version, fw_version, utc_text(last_seen_at)),
        )
        device_id = self.connection.execute("SELECT device_id FROM devices WHERE address=?", (address,)).fetchone()[0]
        self.connection.commit()
        return int(device_id)

    def create_sync(self, device_id: int, *, started_at: str | datetime, source: str, comment: str | None = None) -> int:
        cur = self.connection.execute(
            "INSERT INTO syncs(comment, device_id, timestamp, source) VALUES (?, ?, ?, ?)",
            (comment, device_id, utc_text(started_at), source),
        )
        self.connection.commit()
        return int(cur.lastrowid)

    def finish_sync(self, sync_id: int, *, finished_at: str | datetime) -> None:
        self.connection.execute("UPDATE syncs SET finished_at=? WHERE sync_id=?", (utc_text(finished_at), sync_id))
        self.connection.commit()

    def get_latest_sync_timestamp(self, device_id: int) -> datetime | None:
        row = self.connection.execute(
            "SELECT MAX(timestamp) FROM syncs WHERE device_id=?",
            (device_id,),
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return datetime.fromisoformat(row[0])

    def record_gatt_snapshot(self, device_id: int, sync_id: int, *, observed_at: str | datetime, services: list[dict[str, Any]]) -> None:
        observed_at_text = utc_text(observed_at)
        for service in services:
            for char in service.get("chars", []):
                cur = self.connection.execute(
                    """
                    INSERT INTO gatt_characteristics(device_id, service_uuid, char_uuid, handle, description, properties_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(device_id, char_uuid, handle) DO UPDATE SET
                        description=excluded.description,
                        properties_json=excluded.properties_json
                    """,
                    (
                        device_id,
                        service.get("uuid"),
                        char.get("uuid"),
                        char.get("handle"),
                        service.get("description"),
                        json.dumps(char.get("properties", [])),
                    ),
                )
                _ = cur
                characteristic_id = self.connection.execute(
                    "SELECT characteristic_id FROM gatt_characteristics WHERE device_id=? AND char_uuid=? AND handle IS ?",
                    (device_id, char.get("uuid"), char.get("handle")),
                ).fetchone()[0]
                if "read_value_hex" in char or "read_error" in char:
                    self.connection.execute(
                        """
                        INSERT INTO gatt_reads(characteristic_id, sync_id, timestamp, value_hex, value_text, read_error)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            characteristic_id,
                            sync_id,
                            observed_at_text,
                            char.get("read_value_hex"),
                            char.get("read_value_text"),
                            char.get("read_error"),
                        ),
                    )
        self.connection.commit()

    def record_raw_packet(
        self,
        device_id: int,
        sync_id: int,
        *,
        timestamp: str | datetime,
        direction: str,
        channel_uuid: str,
        packet_hex: str,
        command_id: int | None,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO raw_packets(device_id, sync_id, timestamp, direction, channel_uuid, command_id, packet_hex)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (device_id, sync_id, utc_text(timestamp), direction, channel_uuid, command_id, packet_hex),
        )

    def record_battery(self, device_id: int, sync_id: int, *, timestamp: str | datetime, sample: BatteryStatus, raw_packet_hex: str) -> None:
        self.connection.execute(
            """
            INSERT INTO battery_samples(device_id, sync_id, timestamp, battery_level, charging, raw_packet_hex)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (device_id, sync_id, utc_text(timestamp), sample.battery_level, int(sample.charging), raw_packet_hex),
        )
        self.connection.commit()

    def record_heart_rate_settings(
        self,
        device_id: int,
        sync_id: int,
        *,
        timestamp: str | datetime,
        settings: HeartRateLogSettings,
        raw_packet_hex: str,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO heart_rate_settings(device_id, sync_id, timestamp, enabled, interval_minutes, raw_packet_hex)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (device_id, sync_id, utc_text(timestamp), int(settings.enabled), settings.interval, raw_packet_hex),
        )
        self.connection.commit()

    def record_capabilities(
        self,
        device_id: int,
        sync_id: int,
        *,
        timestamp: str | datetime,
        capabilities: dict[str, Any],
        raw_packet_hex: str,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO capability_snapshots(device_id, sync_id, timestamp, raw_packet_hex, capabilities_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (device_id, sync_id, utc_text(timestamp), raw_packet_hex, json.dumps(capabilities, sort_keys=True)),
        )
        self.connection.commit()

    def record_realtime_samples(
        self,
        device_id: int,
        sync_id: int,
        *,
        observed_at: str | datetime,
        samples: list[tuple[RealTimeSample, str]],
    ) -> None:
        observed_at_text = utc_text(observed_at)
        self.connection.executemany(
            """
            INSERT INTO realtime_samples(device_id, sync_id, timestamp, metric, value, error_code, raw_packet_hex)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (device_id, sync_id, observed_at_text, sample.metric, sample.value, sample.error_code, raw_packet_hex)
                for sample, raw_packet_hex in samples
            ],
        )
        self.connection.commit()

    def record_activity_blocks(
        self,
        device_id: int,
        sync_id: int,
        *,
        blocks: list[ActivityBlock],
        raw_packet_hex: str | None = None,
    ) -> None:
        self.connection.executemany(
            """
            INSERT INTO sport_details(calories, steps, distance, timestamp, device_id, sync_id, time_index, source_command, raw_packet_hex)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(device_id, timestamp) DO UPDATE SET
                calories=excluded.calories,
                steps=excluded.steps,
                distance=excluded.distance,
                sync_id=excluded.sync_id,
                time_index=excluded.time_index,
                source_command=excluded.source_command,
                raw_packet_hex=excluded.raw_packet_hex
            """,
            [
                (
                    block.calories,
                    block.steps,
                    block.distance,
                    utc_text(block.timestamp),
                    device_id,
                    sync_id,
                    block.time_index,
                    67,
                    raw_packet_hex,
                )
                for block in blocks
            ],
        )
        self.connection.commit()

    def record_heart_rate_day(
        self,
        device_id: int,
        sync_id: int,
        *,
        day: HeartRateDay,
        raw_packet_hex: str | None = None,
    ) -> None:
        rows = []
        for reading, timestamp in day.readings_with_times():
            if reading == 0:
                continue
            rows.append((reading, utc_text(timestamp), device_id, sync_id, 21, raw_packet_hex))
        self.connection.executemany(
            """
            INSERT INTO heart_rates(reading, timestamp, device_id, sync_id, source_command, raw_packet_hex)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(device_id, timestamp) DO UPDATE SET
                reading=excluded.reading,
                sync_id=excluded.sync_id,
                source_command=excluded.source_command,
                raw_packet_hex=excluded.raw_packet_hex
            """,
            rows,
        )
        self.connection.commit()

    def record_sleep_sessions(
        self,
        device_id: int,
        sync_id: int,
        *,
        reference: datetime,
        sessions: list[SleepSession],
        raw_packet_hex: str,
        source_command: int,
    ) -> None:
        reference = reference.astimezone(UTC)
        for session in sessions:
            raw_json = to_json(session)
            total_minutes = sum(period.minutes for period in session.periods)
            is_provisional = any(period.stage.startswith("unknown-") for period in session.periods)
            start_timestamp = None
            end_timestamp = None

            if 0 <= session.sleep_start_minutes <= 48 * 60 and 0 <= session.sleep_end_minutes <= 48 * 60:
                start_dt, end_dt = session.resolved_bounds(reference)
                start_timestamp = utc_text(start_dt)
                end_timestamp = utc_text(end_dt)
            else:
                is_provisional = True

            self.connection.execute(
                """
                INSERT INTO sleep_sessions(
                    device_id,
                    sync_id,
                    start_timestamp,
                    end_timestamp,
                    total_minutes,
                    state,
                    score,
                    is_provisional,
                    source_command,
                    raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(device_id, source_command, raw_json) DO UPDATE SET
                    sync_id=excluded.sync_id,
                    start_timestamp=COALESCE(excluded.start_timestamp, sleep_sessions.start_timestamp),
                    end_timestamp=COALESCE(excluded.end_timestamp, sleep_sessions.end_timestamp),
                    total_minutes=excluded.total_minutes,
                    state=excluded.state,
                    score=excluded.score,
                    is_provisional=excluded.is_provisional
                """,
                (
                    device_id,
                    sync_id,
                    start_timestamp,
                    end_timestamp,
                    total_minutes,
                    "decoded",
                    None,
                    int(is_provisional),
                    source_command,
                    raw_json,
                ),
            )
            sleep_session_id = self.connection.execute(
                """
                SELECT sleep_session_id
                FROM sleep_sessions
                WHERE device_id=? AND source_command=? AND raw_json=?
                """,
                (device_id, source_command, raw_json),
            ).fetchone()[0]

            stage_start = datetime.fromisoformat(start_timestamp) if start_timestamp else None
            for index, period in enumerate(session.periods):
                period_start = stage_start
                period_end = None
                if stage_start is not None:
                    period_end = stage_start + timedelta(minutes=period.minutes)
                period_json = to_json(period)
                self.connection.execute(
                    """
                    INSERT INTO sleep_stage_samples(
                        sleep_session_id,
                        device_id,
                        sync_id,
                        sequence_index,
                        stage,
                        start_timestamp,
                        end_timestamp,
                        minutes,
                        is_provisional,
                        raw_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(sleep_session_id, sequence_index) DO UPDATE SET
                        sync_id=excluded.sync_id,
                        stage=excluded.stage,
                        start_timestamp=excluded.start_timestamp,
                        end_timestamp=excluded.end_timestamp,
                        minutes=excluded.minutes,
                        is_provisional=excluded.is_provisional,
                        raw_json=excluded.raw_json
                    """,
                    (
                        sleep_session_id,
                        device_id,
                        sync_id,
                        index,
                        period.stage,
                        utc_text(period_start) if period_start is not None else None,
                        utc_text(period_end) if period_end is not None else None,
                        period.minutes,
                        int(is_provisional or period.stage.startswith("unknown-")),
                        period_json,
                    ),
                )
                if stage_start is not None and period_end is not None:
                    stage_start = period_end
        self.connection.commit()

    def record_blood_oxygen_history(
        self,
        device_id: int,
        sync_id: int,
        *,
        target: datetime,
        history: BloodOxygenHistory,
        raw_packet_hex: str,
        source_command: int,
        interval_minutes: int = 30,
    ) -> None:
        rows = []
        for sample_index, (sample, timestamp) in enumerate(history.samples_with_times(target, interval_minutes=interval_minutes)):
            if sample.min_percent <= 0 or sample.max_percent <= 0:
                continue
            rows.append(
                (
                    device_id,
                    sync_id,
                    utc_text(timestamp),
                    sample_index,
                    sample.min_percent,
                    sample.max_percent,
                    interval_minutes,
                    1,
                    source_command,
                    raw_packet_hex,
                )
            )
        self.connection.executemany(
            """
            INSERT INTO blood_oxygen_samples(
                device_id,
                sync_id,
                timestamp,
                sample_index,
                min_percent,
                max_percent,
                interval_minutes,
                is_provisional,
                source_command,
                raw_packet_hex
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(device_id, timestamp, source_command) DO UPDATE SET
                sync_id=excluded.sync_id,
                sample_index=excluded.sample_index,
                min_percent=excluded.min_percent,
                max_percent=excluded.max_percent,
                interval_minutes=excluded.interval_minutes,
                is_provisional=excluded.is_provisional,
                raw_packet_hex=excluded.raw_packet_hex
            """,
            rows,
        )
        self.connection.commit()

    def record_pressure_history(
        self,
        device_id: int,
        sync_id: int,
        *,
        target: datetime,
        history: PressureHistory,
        raw_packet_hex: str,
        source_command: int,
    ) -> None:
        rows = []
        for sample_index, (value, timestamp) in enumerate(history.readings_with_times(target)):
            if value == 0:
                continue
            rows.append(
                (
                    device_id,
                    sync_id,
                    utc_text(timestamp),
                    sample_index,
                    value,
                    history.range_minutes,
                    source_command,
                    raw_packet_hex,
                )
            )
        self.connection.executemany(
            """
            INSERT INTO pressure_samples(
                device_id,
                sync_id,
                timestamp,
                sample_index,
                value,
                interval_minutes,
                source_command,
                raw_packet_hex
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(device_id, timestamp, source_command) DO UPDATE SET
                sync_id=excluded.sync_id,
                sample_index=excluded.sample_index,
                value=excluded.value,
                interval_minutes=excluded.interval_minutes,
                raw_packet_hex=excluded.raw_packet_hex
            """,
            rows,
        )
        self.connection.commit()

    def record_hrv_history(
        self,
        device_id: int,
        sync_id: int,
        *,
        target: datetime,
        history: HrvHistory,
        raw_packet_hex: str,
        source_command: int,
    ) -> None:
        rows = []
        for sample_index, (value, timestamp) in enumerate(history.readings_with_times(target)):
            if value == 0:
                continue
            rows.append(
                (
                    device_id,
                    sync_id,
                    utc_text(timestamp),
                    sample_index,
                    value,
                    history.range_minutes,
                    source_command,
                    raw_packet_hex,
                )
            )
        self.connection.executemany(
            """
            INSERT INTO hrv_samples(
                device_id,
                sync_id,
                timestamp,
                sample_index,
                value,
                interval_minutes,
                source_command,
                raw_packet_hex
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(device_id, timestamp, source_command) DO UPDATE SET
                sync_id=excluded.sync_id,
                sample_index=excluded.sample_index,
                value=excluded.value,
                interval_minutes=excluded.interval_minutes,
                raw_packet_hex=excluded.raw_packet_hex
            """,
            rows,
        )
        self.connection.commit()
