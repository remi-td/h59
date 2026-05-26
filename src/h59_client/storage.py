"""SQLite storage for H59 raw and decoded sync data."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from h59_client.protocol import ActivityBlock, BatteryStatus, HeartRateDay, HeartRateLogSettings, RealTimeSample


SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
    device_id INTEGER PRIMARY KEY,
    address TEXT NOT NULL UNIQUE,
    name TEXT,
    advertisement_json TEXT,
    hw_version TEXT,
    fw_version TEXT,
    last_seen_at TEXT
);

CREATE TABLE IF NOT EXISTS syncs (
    sync_id INTEGER PRIMARY KEY,
    comment TEXT,
    device_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    finished_at TEXT,
    source TEXT,
    FOREIGN KEY(device_id) REFERENCES devices(device_id)
);

CREATE TABLE IF NOT EXISTS heart_rates (
    heart_rate_id INTEGER PRIMARY KEY,
    reading INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
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
    timestamp TEXT NOT NULL,
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
    timestamp TEXT NOT NULL,
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
    timestamp TEXT NOT NULL,
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
    timestamp TEXT NOT NULL,
    raw_packet_hex TEXT,
    capabilities_json TEXT NOT NULL,
    FOREIGN KEY(device_id) REFERENCES devices(device_id),
    FOREIGN KEY(sync_id) REFERENCES syncs(sync_id)
);

CREATE TABLE IF NOT EXISTS realtime_samples (
    realtime_sample_id INTEGER PRIMARY KEY,
    device_id INTEGER NOT NULL,
    sync_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
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
    timestamp TEXT NOT NULL,
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
    timestamp TEXT NOT NULL,
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
    start_timestamp TEXT,
    end_timestamp TEXT,
    state TEXT,
    score REAL,
    source_command INTEGER,
    raw_json TEXT,
    FOREIGN KEY(device_id) REFERENCES devices(device_id),
    FOREIGN KEY(sync_id) REFERENCES syncs(sync_id)
);
"""


class H59Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(SCHEMA)
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def upsert_device(
        self,
        *,
        address: str,
        name: str | None,
        advertisement: dict[str, Any] | None,
        hw_version: str | None,
        fw_version: str | None,
        last_seen_at: str,
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
            (address, name, advertisement_json, hw_version, fw_version, last_seen_at),
        )
        device_id = self.connection.execute("SELECT device_id FROM devices WHERE address=?", (address,)).fetchone()[0]
        self.connection.commit()
        return int(device_id)

    def create_sync(self, device_id: int, *, started_at: str, source: str, comment: str | None = None) -> int:
        cur = self.connection.execute(
            "INSERT INTO syncs(comment, device_id, timestamp, source) VALUES (?, ?, ?, ?)",
            (comment, device_id, started_at, source),
        )
        self.connection.commit()
        return int(cur.lastrowid)

    def finish_sync(self, sync_id: int, *, finished_at: str) -> None:
        self.connection.execute("UPDATE syncs SET finished_at=? WHERE sync_id=?", (finished_at, sync_id))
        self.connection.commit()

    def get_latest_sync_timestamp(self, device_id: int) -> datetime | None:
        row = self.connection.execute(
            "SELECT MAX(timestamp) FROM syncs WHERE device_id=?",
            (device_id,),
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return datetime.fromisoformat(row[0])

    def record_gatt_snapshot(self, device_id: int, sync_id: int, *, observed_at: str, services: list[dict[str, Any]]) -> None:
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
                            observed_at,
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
        timestamp: str,
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
            (device_id, sync_id, timestamp, direction, channel_uuid, command_id, packet_hex),
        )

    def record_battery(self, device_id: int, sync_id: int, *, timestamp: str, sample: BatteryStatus, raw_packet_hex: str) -> None:
        self.connection.execute(
            """
            INSERT INTO battery_samples(device_id, sync_id, timestamp, battery_level, charging, raw_packet_hex)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (device_id, sync_id, timestamp, sample.battery_level, int(sample.charging), raw_packet_hex),
        )
        self.connection.commit()

    def record_heart_rate_settings(
        self,
        device_id: int,
        sync_id: int,
        *,
        timestamp: str,
        settings: HeartRateLogSettings,
        raw_packet_hex: str,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO heart_rate_settings(device_id, sync_id, timestamp, enabled, interval_minutes, raw_packet_hex)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (device_id, sync_id, timestamp, int(settings.enabled), settings.interval, raw_packet_hex),
        )
        self.connection.commit()

    def record_capabilities(
        self,
        device_id: int,
        sync_id: int,
        *,
        timestamp: str,
        capabilities: dict[str, Any],
        raw_packet_hex: str,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO capability_snapshots(device_id, sync_id, timestamp, raw_packet_hex, capabilities_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (device_id, sync_id, timestamp, raw_packet_hex, json.dumps(capabilities, sort_keys=True)),
        )
        self.connection.commit()

    def record_realtime_samples(
        self,
        device_id: int,
        sync_id: int,
        *,
        observed_at: str,
        samples: list[tuple[RealTimeSample, str]],
    ) -> None:
        self.connection.executemany(
            """
            INSERT INTO realtime_samples(device_id, sync_id, timestamp, metric, value, error_code, raw_packet_hex)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (device_id, sync_id, observed_at, sample.metric, sample.value, sample.error_code, raw_packet_hex)
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
                    block.timestamp.isoformat(),
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
            rows.append((reading, timestamp.isoformat(), device_id, sync_id, 21, raw_packet_hex))
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
