"""SQLite storage for H59 raw and decoded sync data."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from h59_client.analytics import ensure_analytic_views
from h59_client.protocol import (
    CMD_START_REAL_TIME,
    ActivityBlock,
    BatteryStatus,
    BloodPressureReading,
    BloodOxygenHistory,
    HeartRateDay,
    HeartRateLogSettings,
    HrvHistory,
    PressureHistory,
    RealTimeSample,
    SleepSession,
    to_json,
)


@dataclass(frozen=True)
class RealtimeObservation:
    metric_code: str
    timestamp: str | datetime
    value_numeric: float | int | None = None
    value_text: str | None = None
    error_code: int = 0
    raw_packet_hex: str | None = None
    source_command: int | None = None
    metric_label: str | None = None
    unit: str | None = None
    description: str | None = None


REALTIME_METRIC_CODE_SEEDS: dict[str, dict[str, str | None]] = {
    "heart-rate": {
        "label": "Heart rate",
        "unit": "bpm",
        "description": "Realtime heart-rate sample requested from the device.",
    },
    "blood-pressure": {
        "label": "Blood pressure stream",
        "unit": None,
        "description": "Opaque realtime stream advertised as blood pressure by the device family.",
    },
    "spo2": {
        "label": "Blood oxygen",
        "unit": "%",
        "description": "Realtime blood-oxygen sample requested from the device.",
    },
    "fatigue": {
        "label": "Fatigue",
        "unit": None,
        "description": "Realtime fatigue-like vendor metric.",
    },
    "health-check": {
        "label": "Health check",
        "unit": None,
        "description": "Realtime one-key health-check workflow sample.",
    },
    "health-check.diastolic": {
        "label": "Health check diastolic",
        "unit": "mmHg",
        "description": "Diastolic blood-pressure result inferred from a health-check packet.",
    },
    "health-check.systolic": {
        "label": "Health check systolic",
        "unit": "mmHg",
        "description": "Systolic blood-pressure result inferred from a health-check packet.",
    },
    "health-check.heart-rate": {
        "label": "Health check heart rate",
        "unit": "bpm",
        "description": "Heart-rate result inferred from a health-check packet.",
    },
    "health-check.cuff-pressure-tenths": {
        "label": "Health check cuff pressure",
        "unit": "tenths",
        "description": "Opaque live cuff-pressure-like value emitted during a health-check workflow.",
    },
    "ecg": {
        "label": "ECG",
        "unit": None,
        "description": "Realtime ECG-like stream exposed by the device family.",
    },
    "pressure": {
        "label": "Pressure / stress-like",
        "unit": None,
        "description": "Realtime pressure or stress-like vendor score.",
    },
    "blood-sugar": {
        "label": "Blood sugar",
        "unit": None,
        "description": "Realtime blood-sugar-like vendor metric.",
    },
    "hrv": {
        "label": "HRV",
        "unit": "ms",
        "description": "Realtime HRV-like vendor metric.",
    },
}


SCHEMA = """
CREATE TABLE IF NOT EXISTS database_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS devices (
    device_id INTEGER PRIMARY KEY,
    address TEXT NOT NULL UNIQUE,
    name TEXT,
    nickname TEXT,
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

CREATE TABLE IF NOT EXISTS metric_codes (
    metric_code_id INTEGER PRIMARY KEY,
    metric_code TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL,
    unit TEXT,
    description TEXT
);

CREATE TABLE IF NOT EXISTS realtime_samples (
    realtime_sample_id INTEGER PRIMARY KEY,
    device_id INTEGER NOT NULL,
    sync_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL CHECK (substr(timestamp, -6) = '+00:00'),
    metric TEXT NOT NULL,
    value INTEGER NOT NULL,
    error_code INTEGER NOT NULL DEFAULT 0,
    metric_code_id INTEGER,
    value_numeric REAL,
    value_text TEXT,
    source_command INTEGER,
    raw_packet_hex TEXT,
    FOREIGN KEY(metric_code_id) REFERENCES metric_codes(metric_code_id),
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

CREATE TABLE IF NOT EXISTS blood_pressure_readings (
    blood_pressure_reading_id INTEGER PRIMARY KEY,
    device_id INTEGER NOT NULL,
    sync_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL CHECK (substr(timestamp, -6) = '+00:00'),
    systolic INTEGER NOT NULL,
    diastolic INTEGER NOT NULL,
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


def normalize_sleep_stage(stage: str) -> str:
    # The raw protocol still carries the original stage code in JSON.
    # Persist the inferred canonical label in the first-class column.
    if stage.startswith("unknown-"):
        return "rem"
    return stage


MIGRATION_SOURCE_CODE = "db.merge_history"

MIGRATABLE_TIMESTAMP_TABLES: dict[str, dict[str, Any]] = {
    "heart_rates": {
        "timestamp_column": "timestamp",
        "select_columns": ["reading", "timestamp", "source_command", "raw_packet_hex"],
        "insert_sql": """
            INSERT OR IGNORE INTO heart_rates(reading, timestamp, device_id, sync_id, source_command, raw_packet_hex)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
    },
    "sport_details": {
        "timestamp_column": "timestamp",
        "select_columns": ["calories", "steps", "distance", "timestamp", "time_index", "source_command", "raw_packet_hex"],
        "insert_sql": """
            INSERT OR IGNORE INTO sport_details(calories, steps, distance, timestamp, device_id, sync_id, time_index, source_command, raw_packet_hex)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
    },
    "battery_samples": {
        "timestamp_column": "timestamp",
        "select_columns": ["timestamp", "battery_level", "charging", "raw_packet_hex"],
        "insert_sql": """
            INSERT INTO battery_samples(device_id, sync_id, timestamp, battery_level, charging, raw_packet_hex)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
    },
    "realtime_samples": {
        "timestamp_column": "timestamp",
        "select_columns": ["timestamp", "metric", "value", "error_code", "raw_packet_hex"],
        "insert_sql": """
            INSERT INTO realtime_samples(
                device_id,
                sync_id,
                timestamp,
                metric,
                value,
                error_code,
                metric_code_id,
                value_numeric,
                value_text,
                source_command,
                raw_packet_hex
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
    },
    "blood_oxygen_samples": {
        "timestamp_column": "timestamp",
        "select_columns": ["timestamp", "sample_index", "min_percent", "max_percent", "interval_minutes", "is_provisional", "source_command", "raw_packet_hex"],
        "insert_sql": """
            INSERT OR IGNORE INTO blood_oxygen_samples(device_id, sync_id, timestamp, sample_index, min_percent, max_percent, interval_minutes, is_provisional, source_command, raw_packet_hex)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
    },
    "blood_pressure_readings": {
        "timestamp_column": "timestamp",
        "select_columns": ["timestamp", "systolic", "diastolic", "source_command", "raw_packet_hex"],
        "insert_sql": """
            INSERT OR IGNORE INTO blood_pressure_readings(device_id, sync_id, timestamp, systolic, diastolic, source_command, raw_packet_hex)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
    },
    "pressure_samples": {
        "timestamp_column": "timestamp",
        "select_columns": ["timestamp", "sample_index", "value", "interval_minutes", "source_command", "raw_packet_hex"],
        "insert_sql": """
            INSERT OR IGNORE INTO pressure_samples(device_id, sync_id, timestamp, sample_index, value, interval_minutes, source_command, raw_packet_hex)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
    },
    "hrv_samples": {
        "timestamp_column": "timestamp",
        "select_columns": ["timestamp", "sample_index", "value", "interval_minutes", "source_command", "raw_packet_hex"],
        "insert_sql": """
            INSERT OR IGNORE INTO hrv_samples(device_id, sync_id, timestamp, sample_index, value, interval_minutes, source_command, raw_packet_hex)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
    },
}


class H59Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(SCHEMA)
        self._apply_migrations()
        self._cleanup_legacy_rows()
        ensure_analytic_views(self.connection)
        self._write_metadata_defaults()
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def _earliest_timestamp(self, table: str, device_id: int, timestamp_column: str) -> datetime | None:
        row = self.connection.execute(
            f"SELECT MIN({timestamp_column}) FROM {table} WHERE device_id=?",
            (device_id,),
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return datetime.fromisoformat(str(row[0]))

    @staticmethod
    def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        return row is not None

    @staticmethod
    def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
        return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}

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

    def _apply_migrations(self) -> None:
        columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(devices)").fetchall()}
        if "nickname" not in columns:
            self.connection.execute("ALTER TABLE devices ADD COLUMN nickname TEXT")
        self.connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_devices_nickname_unique
            ON devices(nickname)
            WHERE nickname IS NOT NULL
            """
        )
        realtime_columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(realtime_samples)").fetchall()}
        if "metric_code_id" not in realtime_columns:
            self.connection.execute("ALTER TABLE realtime_samples ADD COLUMN metric_code_id INTEGER")
        if "value_numeric" not in realtime_columns:
            self.connection.execute("ALTER TABLE realtime_samples ADD COLUMN value_numeric REAL")
        if "value_text" not in realtime_columns:
            self.connection.execute("ALTER TABLE realtime_samples ADD COLUMN value_text TEXT")
        if "source_command" not in realtime_columns:
            self.connection.execute("ALTER TABLE realtime_samples ADD COLUMN source_command INTEGER")
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS metric_codes (
                metric_code_id INTEGER PRIMARY KEY,
                metric_code TEXT NOT NULL UNIQUE,
                label TEXT NOT NULL,
                unit TEXT,
                description TEXT
            )
            """
        )
        self.connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_realtime_samples_metric_code_timestamp
            ON realtime_samples(metric_code_id, timestamp)
            """
        )
        self._seed_metric_codes()
        self._backfill_realtime_metric_codes()

    def _seed_metric_codes(self) -> None:
        self.connection.executemany(
            """
            INSERT INTO metric_codes(metric_code, label, unit, description)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(metric_code) DO UPDATE SET
                label=excluded.label,
                unit=excluded.unit,
                description=excluded.description
            """,
            [
                (metric_code, seed["label"], seed["unit"], seed["description"])
                for metric_code, seed in REALTIME_METRIC_CODE_SEEDS.items()
            ],
        )

    def _ensure_metric_code(
        self,
        metric_code: str,
        *,
        label: str | None = None,
        unit: str | None = None,
        description: str | None = None,
    ) -> int:
        defaults = REALTIME_METRIC_CODE_SEEDS.get(metric_code, {})
        metric_label = label or defaults.get("label") or metric_code.replace("-", " ").replace(".", " / ").title()
        metric_unit = unit if unit is not None else defaults.get("unit")
        metric_description = description if description is not None else defaults.get("description")
        self.connection.execute(
            """
            INSERT INTO metric_codes(metric_code, label, unit, description)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(metric_code) DO UPDATE SET
                label=COALESCE(excluded.label, metric_codes.label),
                unit=COALESCE(excluded.unit, metric_codes.unit),
                description=COALESCE(excluded.description, metric_codes.description)
            """,
            (metric_code, metric_label, metric_unit, metric_description),
        )
        row = self.connection.execute(
            "SELECT metric_code_id FROM metric_codes WHERE metric_code=?",
            (metric_code,),
        ).fetchone()
        if row is None:
            raise ValueError(f"failed to resolve metric code id for {metric_code}")
        return int(row["metric_code_id"])

    def _backfill_realtime_metric_codes(self) -> None:
        rows = self.connection.execute(
            """
            SELECT realtime_sample_id, metric, value, metric_code_id, value_numeric, source_command
            FROM realtime_samples
            WHERE metric_code_id IS NULL OR value_numeric IS NULL OR source_command IS NULL
            """
        ).fetchall()
        for row in rows:
            metric_code = str(row["metric"])
            metric_code_id = self._ensure_metric_code(metric_code)
            value_numeric = row["value_numeric"]
            if value_numeric is None:
                value_numeric = float(row["value"])
            source_command = row["source_command"] if row["source_command"] is not None else CMD_START_REAL_TIME
            self.connection.execute(
                """
                UPDATE realtime_samples
                SET metric_code_id=?,
                    value_numeric=?,
                    source_command=?
                WHERE realtime_sample_id=?
                """,
                (metric_code_id, value_numeric, source_command, int(row["realtime_sample_id"])),
            )

    def _cleanup_legacy_rows(self) -> None:
        # Older builds could persist malformed sleep rows without resolved
        # timestamps. Raw packets remain available, so remove only the broken
        # first-class decoded rows.
        self.connection.execute(
            """
            DELETE FROM sleep_stage_samples
            WHERE start_timestamp IS NULL OR end_timestamp IS NULL
            """
        )
        self.connection.execute(
            """
            DELETE FROM sleep_sessions
            WHERE start_timestamp IS NULL
               OR end_timestamp IS NULL
               OR total_minutes IS NULL
               OR total_minutes <= 0
            """
        )
        # Historical sleep decoding used `unknown-*` stage labels for a stage
        # we now interpret as REM. Keep the raw JSON intact, but normalize the
        # first-class stage column for analytics and dashboard use.
        self.connection.execute(
            """
            UPDATE sleep_stage_samples
            SET stage='rem', is_provisional=1
            WHERE stage LIKE 'unknown-%'
            """
        )
        self.connection.execute(
            """
            UPDATE sleep_sessions
            SET is_provisional=1
            WHERE sleep_session_id IN (
                SELECT DISTINCT sleep_session_id
                FROM sleep_stage_samples
                WHERE is_provisional=1
            )
            """
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

    def get_device_by_selector(self, selector: str) -> sqlite3.Row | None:
        if selector.isdigit():
            row = self.connection.execute("SELECT * FROM devices WHERE device_id=?", (int(selector),)).fetchone()
            if row is not None:
                return row
        row = self.connection.execute("SELECT * FROM devices WHERE address=?", (selector,)).fetchone()
        if row is not None:
            return row
        row = self.connection.execute("SELECT * FROM devices WHERE nickname=?", (selector,)).fetchone()
        if row is not None:
            return row
        return self.connection.execute("SELECT * FROM devices WHERE name=?", (selector,)).fetchone()

    def list_devices(self) -> list[sqlite3.Row]:
        rows = self.connection.execute(
            """
            SELECT device_id, address, name, nickname, hw_version, fw_version, last_seen_at
            FROM devices
            ORDER BY
                CASE WHEN nickname IS NULL THEN 1 ELSE 0 END,
                nickname ASC,
                CASE WHEN last_seen_at IS NULL THEN 1 ELSE 0 END,
                last_seen_at DESC,
                device_id ASC
            """
        ).fetchall()
        return list(rows)

    def get_preferred_device(self, *, name: str | None = None) -> sqlite3.Row | None:
        if name and name != "H59":
            row = self.connection.execute(
                """
                SELECT *
                FROM devices
                WHERE name=?
                ORDER BY
                    CASE WHEN last_seen_at IS NULL THEN 1 ELSE 0 END,
                    last_seen_at DESC,
                    device_id ASC
                LIMIT 1
                """,
                (name,),
            ).fetchone()
            if row is not None:
                return row
            return None

        return self.connection.execute(
            """
            SELECT *
            FROM devices
            ORDER BY
                CASE WHEN last_seen_at IS NULL THEN 1 ELSE 0 END,
                last_seen_at DESC,
                device_id ASC
            LIMIT 1
            """
        ).fetchone()

    def set_device_nickname(self, selector: str, nickname: str | None) -> sqlite3.Row:
        row = self.get_device_by_selector(selector)
        if row is None:
            raise ValueError(f"unknown device selector: {selector}")
        normalized = nickname.strip() if nickname is not None else None
        if normalized == "":
            normalized = None
        self.connection.execute(
            "UPDATE devices SET nickname=? WHERE device_id=?",
            (normalized, int(row["device_id"])),
        )
        self.connection.commit()
        updated = self.connection.execute("SELECT * FROM devices WHERE device_id=?", (int(row["device_id"]),)).fetchone()
        if updated is None:
            raise ValueError(f"device disappeared during nickname update: {selector}")
        return updated

    def has_gatt_snapshot(self, device_id: int) -> bool:
        row = self.connection.execute(
            "SELECT 1 FROM gatt_characteristics WHERE device_id=? LIMIT 1",
            (device_id,),
        ).fetchone()
        return row is not None

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

    def merge_history_from(
        self,
        source_path: str | Path,
        *,
        migration_source: str = MIGRATION_SOURCE_CODE,
    ) -> dict[str, Any]:
        source_db_path = Path(source_path).expanduser().resolve()
        target_db_path = self.path.expanduser().resolve()
        if source_db_path == target_db_path:
            raise ValueError("source and target databases must be different")
        if not source_db_path.exists():
            raise ValueError(f"source database does not exist: {source_db_path}")

        source_conn = sqlite3.connect(source_db_path)
        source_conn.row_factory = sqlite3.Row
        try:
            source_devices = source_conn.execute(
                """
                SELECT device_id, address, name, advertisement_json, hw_version, fw_version, last_seen_at
                FROM devices
                ORDER BY device_id ASC
                """
            ).fetchall()
            merged_devices: list[dict[str, Any]] = []
            for source_device in source_devices:
                existing_target_row = self.connection.execute(
                    "SELECT device_id FROM devices WHERE address=?",
                    (str(source_device["address"]),),
                ).fetchone()
                target_device_id = self.upsert_device(
                    address=str(source_device["address"]),
                    name=source_device["name"],
                    advertisement=json.loads(source_device["advertisement_json"]) if source_device["advertisement_json"] else None,
                    hw_version=source_device["hw_version"],
                    fw_version=source_device["fw_version"],
                    last_seen_at=source_device["last_seen_at"] or datetime.now(UTC),
                )
                device_summary = self._merge_device_history(
                    source_conn,
                    source_device_id=int(source_device["device_id"]),
                    target_device_id=target_device_id,
                    target_address=str(source_device["address"]),
                    source_db_path=source_db_path,
                    migration_source=migration_source,
                )
                if device_summary["imported_rows"] > 0:
                    merged_devices.append(device_summary)
                elif existing_target_row is None:
                    self.connection.execute("DELETE FROM devices WHERE device_id=?", (target_device_id,))
            self.connection.commit()
            return {
                "source_db": str(source_db_path),
                "target_db": str(target_db_path),
                "migration_source": migration_source,
                "devices": merged_devices,
                "imported_rows": sum(int(device["imported_rows"]) for device in merged_devices),
            }
        finally:
            source_conn.close()

    def _merge_device_history(
        self,
        source_conn: sqlite3.Connection,
        *,
        source_device_id: int,
        target_device_id: int,
        target_address: str,
        source_db_path: Path,
        migration_source: str,
    ) -> dict[str, Any]:
        per_entity: dict[str, int] = {}
        migration_sync_id: int | None = None

        def ensure_sync() -> int:
            nonlocal migration_sync_id
            if migration_sync_id is None:
                started_at = datetime.now(UTC)
                comment = f"history merge from {source_db_path}"
                migration_sync_id = self.create_sync(
                    target_device_id,
                    started_at=started_at,
                    source=migration_source,
                    comment=comment,
                )
                self.finish_sync(migration_sync_id, finished_at=started_at)
            return migration_sync_id

        for table, config in MIGRATABLE_TIMESTAMP_TABLES.items():
            count = self._merge_timestamp_table(
                source_conn,
                table=table,
                source_device_id=source_device_id,
                target_device_id=target_device_id,
                timestamp_column=str(config["timestamp_column"]),
                select_columns=list(config["select_columns"]),
                insert_sql=str(config["insert_sql"]),
                sync_id_factory=ensure_sync,
            )
            per_entity[table] = count

        sleep_counts = self._merge_sleep_history(
            source_conn,
            source_device_id=source_device_id,
            target_device_id=target_device_id,
            sync_id_factory=ensure_sync,
        )
        per_entity.update(sleep_counts)

        imported_rows = sum(per_entity.values())
        return {
            "source_device_id": source_device_id,
            "target_device_id": target_device_id,
            "address": target_address,
            "sync_id": migration_sync_id,
            "imported_rows": imported_rows,
            "entities": per_entity,
        }

    def _merge_timestamp_table(
        self,
        source_conn: sqlite3.Connection,
        *,
        table: str,
        source_device_id: int,
        target_device_id: int,
        timestamp_column: str,
        select_columns: list[str],
        insert_sql: str,
        sync_id_factory: Any,
    ) -> int:
        if not self._table_exists(source_conn, table):
            return 0
        earliest_target = self._earliest_timestamp(table, target_device_id, timestamp_column)
        source_columns = self._table_columns(source_conn, table)
        if table == "realtime_samples":
            if self._table_exists(source_conn, "metric_codes") and "metric_code_id" in source_columns:
                source_rows = source_conn.execute(
                    """
                    SELECT
                        rs.timestamp,
                        rs.metric,
                        rs.value,
                        rs.error_code,
                        rs.raw_packet_hex,
                        rs.value_numeric,
                        rs.value_text,
                        rs.source_command,
                        mc.metric_code
                    FROM realtime_samples AS rs
                    LEFT JOIN metric_codes AS mc
                      ON mc.metric_code_id = rs.metric_code_id
                    WHERE rs.device_id=?
                    ORDER BY rs.timestamp ASC
                    """,
                    (source_device_id,),
                ).fetchall()
            else:
                source_rows = source_conn.execute(
                    """
                    SELECT timestamp, metric, value, error_code, raw_packet_hex
                    FROM realtime_samples
                    WHERE device_id=?
                    ORDER BY timestamp ASC
                    """,
                    (source_device_id,),
                ).fetchall()
        else:
            source_rows = source_conn.execute(
                f"""
                SELECT {", ".join(select_columns)}
                FROM {table}
                WHERE device_id=?
                ORDER BY {timestamp_column} ASC
                """,
                (source_device_id,),
            ).fetchall()
        if not source_rows:
            return 0

        rows_to_insert: list[tuple[Any, ...]] = []
        for row in source_rows:
            row_ts = datetime.fromisoformat(str(row[timestamp_column]))
            if earliest_target is not None and row_ts >= earliest_target:
                continue
            sync_id = sync_id_factory()
            if table == "heart_rates":
                rows_to_insert.append((row["reading"], utc_text(row["timestamp"]), target_device_id, sync_id, row["source_command"], row["raw_packet_hex"]))
            elif table == "sport_details":
                rows_to_insert.append(
                    (
                        row["calories"],
                        row["steps"],
                        row["distance"],
                        utc_text(row["timestamp"]),
                        target_device_id,
                        sync_id,
                        row["time_index"],
                        row["source_command"],
                        row["raw_packet_hex"],
                    )
                )
            elif table == "battery_samples":
                rows_to_insert.append(
                    (
                        target_device_id,
                        sync_id,
                        utc_text(row["timestamp"]),
                        row["battery_level"],
                        row["charging"],
                        row["raw_packet_hex"],
                    )
                )
            elif table == "realtime_samples":
                metric_code = row["metric"]
                if "metric_code" in row.keys() and row["metric_code"]:
                    metric_code = row["metric_code"]
                metric_code_id = self._ensure_metric_code(str(metric_code))
                value_numeric = row["value_numeric"] if "value_numeric" in row.keys() else row["value"]
                source_command = row["source_command"] if "source_command" in row.keys() else CMD_START_REAL_TIME
                rows_to_insert.append(
                    (
                        target_device_id,
                        sync_id,
                        utc_text(row["timestamp"]),
                        str(metric_code),
                        int(float(value_numeric)) if value_numeric is not None else 0,
                        row["error_code"],
                        metric_code_id,
                        value_numeric,
                        row["value_text"] if "value_text" in row.keys() else None,
                        source_command,
                        row["raw_packet_hex"],
                    )
                )
            elif table == "blood_oxygen_samples":
                rows_to_insert.append(
                    (
                        target_device_id,
                        sync_id,
                        utc_text(row["timestamp"]),
                        row["sample_index"],
                        row["min_percent"],
                        row["max_percent"],
                        row["interval_minutes"],
                        row["is_provisional"],
                        row["source_command"],
                        row["raw_packet_hex"],
                    )
                )
            elif table == "blood_pressure_readings":
                rows_to_insert.append(
                    (
                        target_device_id,
                        sync_id,
                        utc_text(row["timestamp"]),
                        row["systolic"],
                        row["diastolic"],
                        row["source_command"],
                        row["raw_packet_hex"],
                    )
                )
            elif table == "pressure_samples":
                rows_to_insert.append(
                    (
                        target_device_id,
                        sync_id,
                        utc_text(row["timestamp"]),
                        row["sample_index"],
                        row["value"],
                        row["interval_minutes"],
                        row["source_command"],
                        row["raw_packet_hex"],
                    )
                )
            elif table == "hrv_samples":
                rows_to_insert.append(
                    (
                        target_device_id,
                        sync_id,
                        utc_text(row["timestamp"]),
                        row["sample_index"],
                        row["value"],
                        row["interval_minutes"],
                        row["source_command"],
                        row["raw_packet_hex"],
                    )
                )
            else:
                raise ValueError(f"unsupported migration table: {table}")

        if not rows_to_insert:
            return 0
        before = self.connection.total_changes
        self.connection.executemany(insert_sql, rows_to_insert)
        return self.connection.total_changes - before

    def _merge_sleep_history(
        self,
        source_conn: sqlite3.Connection,
        *,
        source_device_id: int,
        target_device_id: int,
        sync_id_factory: Any,
    ) -> dict[str, int]:
        if not self._table_exists(source_conn, "sleep_sessions"):
            return {"sleep_sessions": 0, "sleep_stage_samples": 0}
        earliest_target = self._earliest_timestamp("sleep_sessions", target_device_id, "end_timestamp")
        source_sessions = source_conn.execute(
            """
            SELECT *
            FROM sleep_sessions
            WHERE device_id=?
            ORDER BY end_timestamp ASC, start_timestamp ASC
            """,
            (source_device_id,),
        ).fetchall()
        imported_sessions = 0
        imported_stages = 0
        for session in source_sessions:
            effective_ts = session["end_timestamp"] or session["start_timestamp"]
            if effective_ts is None:
                continue
            if earliest_target is not None and datetime.fromisoformat(str(effective_ts)) >= earliest_target:
                continue
            sync_id = sync_id_factory()
            before = self.connection.total_changes
            cur = self.connection.execute(
                """
                INSERT OR IGNORE INTO sleep_sessions(
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
                """,
                (
                    target_device_id,
                    sync_id,
                    session["start_timestamp"],
                    session["end_timestamp"],
                    session["total_minutes"],
                    session["state"],
                    session["score"],
                    session["is_provisional"],
                    session["source_command"],
                    session["raw_json"],
                ),
            )
            inserted_session = self.connection.total_changes > before
            target_sleep_session_id = int(cur.lastrowid) if inserted_session else int(
                self.connection.execute(
                    """
                    SELECT sleep_session_id
                    FROM sleep_sessions
                    WHERE device_id=? AND source_command=? AND raw_json=?
                    """,
                    (target_device_id, session["source_command"], session["raw_json"]),
                ).fetchone()[0]
            )
            if inserted_session:
                imported_sessions += 1
                if not self._table_exists(source_conn, "sleep_stage_samples"):
                    continue
                stage_rows = source_conn.execute(
                    """
                    SELECT sequence_index, stage, start_timestamp, end_timestamp, minutes, is_provisional, raw_json
                    FROM sleep_stage_samples
                    WHERE sleep_session_id=?
                    ORDER BY sequence_index ASC
                    """,
                    (int(session["sleep_session_id"]),),
                ).fetchall()
                before = self.connection.total_changes
                self.connection.executemany(
                    """
                    INSERT OR IGNORE INTO sleep_stage_samples(
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
                    """,
                    [
                        (
                            target_sleep_session_id,
                            target_device_id,
                            sync_id,
                            row["sequence_index"],
                            normalize_sleep_stage(str(row["stage"])),
                            row["start_timestamp"],
                            row["end_timestamp"],
                            row["minutes"],
                            row["is_provisional"],
                            row["raw_json"],
                        )
                        for row in stage_rows
                    ],
                )
                imported_stages += self.connection.total_changes - before
        return {
            "sleep_sessions": imported_sessions,
            "sleep_stage_samples": imported_stages,
        }

    def _get_latest_metric_timestamp(self, table: str, device_id: int) -> datetime | None:
        row = self.connection.execute(
            f"SELECT MAX(timestamp) FROM {table} WHERE device_id=?",
            (device_id,),
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return datetime.fromisoformat(row[0])

    def _overlap_cutoff(
        self,
        *,
        table: str,
        device_id: int,
        target_day: datetime,
        interval_minutes: int,
        overlap_periods: int = 1,
    ) -> datetime | None:
        latest = self._get_latest_metric_timestamp(table, device_id)
        if latest is None:
            return None
        if latest.astimezone(UTC).date() != target_day.astimezone(UTC).date():
            return None
        return latest - timedelta(minutes=interval_minutes * overlap_periods)

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

    def get_latest_capabilities(self, device_id: int) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT capabilities_json
            FROM capability_snapshots
            WHERE device_id=?
            ORDER BY timestamp DESC, capability_snapshot_id DESC
            LIMIT 1
            """,
            (device_id,),
        ).fetchone()
        if row is None or row["capabilities_json"] is None:
            return None
        return json.loads(str(row["capabilities_json"]))

    def record_realtime_samples(
        self,
        device_id: int,
        sync_id: int,
        *,
        observed_at: str | datetime,
        samples: list[tuple[RealTimeSample, str]],
    ) -> None:
        self.record_realtime_observations(
            device_id,
            sync_id,
            observations=[
                RealtimeObservation(
                    metric_code=sample.metric,
                    timestamp=observed_at,
                    value_numeric=sample.value,
                    error_code=sample.error_code,
                    raw_packet_hex=raw_packet_hex,
                    source_command=CMD_START_REAL_TIME,
                )
                for sample, raw_packet_hex in samples
            ],
        )

    def record_realtime_observations(
        self,
        device_id: int,
        sync_id: int,
        *,
        observations: list[RealtimeObservation],
    ) -> None:
        if not observations:
            return
        rows_to_insert: list[tuple[Any, ...]] = []
        for observation in observations:
            metric_code_id = self._ensure_metric_code(
                observation.metric_code,
                label=observation.metric_label,
                unit=observation.unit,
                description=observation.description,
            )
            value_numeric = None if observation.value_numeric is None else float(observation.value_numeric)
            legacy_value = int(round(value_numeric)) if value_numeric is not None else 0
            rows_to_insert.append(
                (
                    device_id,
                    sync_id,
                    utc_text(observation.timestamp),
                    observation.metric_code,
                    legacy_value,
                    observation.error_code,
                    metric_code_id,
                    value_numeric,
                    observation.value_text,
                    observation.source_command,
                    observation.raw_packet_hex,
                )
            )
        self.connection.executemany(
            """
            INSERT INTO realtime_samples(
                device_id,
                sync_id,
                timestamp,
                metric,
                value,
                error_code,
                metric_code_id,
                value_numeric,
                value_text,
                source_command,
                raw_packet_hex
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows_to_insert,
        )
        self.connection.commit()

    def record_blood_pressure_readings(
        self,
        device_id: int,
        sync_id: int,
        *,
        readings: list[BloodPressureReading],
        raw_packet_hex: str | None = None,
        source_command: int = 20,
    ) -> None:
        if not readings:
            return
        self.connection.executemany(
            """
            INSERT INTO blood_pressure_readings(device_id, sync_id, timestamp, systolic, diastolic, source_command, raw_packet_hex)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(device_id, timestamp, source_command) DO UPDATE SET
                systolic=excluded.systolic,
                diastolic=excluded.diastolic,
                sync_id=excluded.sync_id,
                raw_packet_hex=excluded.raw_packet_hex
            """,
            [
                (
                    device_id,
                    sync_id,
                    utc_text(reading.timestamp),
                    reading.systolic,
                    reading.diastolic,
                    source_command,
                    raw_packet_hex,
                )
                for reading in readings
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
        if not blocks:
            return
        cutoff = self._overlap_cutoff(
            table="sport_details",
            device_id=device_id,
            target_day=blocks[0].timestamp,
            interval_minutes=15,
        )
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
                if cutoff is None or block.timestamp >= cutoff
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
        cutoff = self._overlap_cutoff(
            table="heart_rates",
            device_id=device_id,
            target_day=day.timestamp,
            interval_minutes=max(1, day.range),
        )
        rows = []
        for reading, timestamp in day.readings_with_times():
            if reading == 0:
                continue
            if cutoff is not None and timestamp < cutoff:
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
            if not session.has_valid_bounds():
                continue
            raw_json = to_json(session)
            total_minutes = sum(period.minutes for period in session.periods)
            if total_minutes <= 0:
                continue
            is_provisional = any(period.stage.startswith("unknown-") for period in session.periods)
            start_dt, end_dt = session.resolved_bounds(reference)
            start_timestamp = utc_text(start_dt)
            end_timestamp = utc_text(end_dt)
            existing_row = self.connection.execute(
                """
                SELECT sleep_session_id
                FROM sleep_sessions
                WHERE device_id=? AND source_command=? AND raw_json=?
                ORDER BY sleep_session_id DESC
                LIMIT 1
                """,
                (device_id, source_command, raw_json),
            ).fetchone()
            if existing_row is None:
                existing_row = self.connection.execute(
                    """
                    SELECT sleep_session_id
                    FROM sleep_sessions
                    WHERE device_id=? AND source_command=? AND start_timestamp=? AND end_timestamp=?
                    ORDER BY sleep_session_id DESC
                    LIMIT 1
                    """,
                    (device_id, source_command, start_timestamp, end_timestamp),
                ).fetchone()
            if existing_row is not None:
                sleep_session_id = int(existing_row[0])
                self.connection.execute(
                    """
                    UPDATE sleep_sessions
                    SET
                        sync_id=?,
                        start_timestamp=?,
                        end_timestamp=?,
                        total_minutes=?,
                        state=?,
                        score=?,
                        is_provisional=?,
                        raw_json=?
                    WHERE sleep_session_id=?
                    """,
                    (
                        sync_id,
                        start_timestamp,
                        end_timestamp,
                        total_minutes,
                        "decoded",
                        None,
                        int(is_provisional),
                        raw_json,
                        sleep_session_id,
                    ),
                )
                self.connection.execute(
                    "DELETE FROM sleep_stage_samples WHERE sleep_session_id=?",
                    (sleep_session_id,),
                )
            else:
                cur = self.connection.execute(
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
                sleep_session_id = int(cur.lastrowid)

            stage_start = datetime.fromisoformat(start_timestamp)
            for index, period in enumerate(session.periods):
                period_start = stage_start
                period_end = stage_start + timedelta(minutes=period.minutes)
                period_json = to_json(period)
                normalized_stage = normalize_sleep_stage(period.stage)
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
                        normalized_stage,
                        utc_text(period_start),
                        utc_text(period_end),
                        period.minutes,
                        int(is_provisional or period.stage.startswith("unknown-")),
                        period_json,
                    ),
                )
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
        device_clock_mode: str = "utc",
    ) -> None:
        interval_minutes = history.interval_minutes
        cutoff = (
            self._overlap_cutoff(
                table="blood_oxygen_samples",
                device_id=device_id,
                target_day=target,
                interval_minutes=interval_minutes,
            )
            if device_clock_mode == "utc"
            else None
        )
        rows = []
        for offset, (sample, timestamp) in enumerate(history.samples_with_times(target, clock_mode=device_clock_mode)):
            if sample.min_percent <= 0 or sample.max_percent <= 0:
                continue
            if cutoff is not None and timestamp < cutoff:
                continue
            sample_index = history.start_index + offset
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
        device_clock_mode: str = "utc",
    ) -> None:
        cutoff = (
            self._overlap_cutoff(
                table="pressure_samples",
                device_id=device_id,
                target_day=target,
                interval_minutes=max(1, history.range_minutes),
            )
            if device_clock_mode == "utc"
            else None
        )
        rows = []
        for sample_index, (value, timestamp) in enumerate(history.readings_with_times(target, clock_mode=device_clock_mode)):
            if value == 0:
                continue
            if cutoff is not None and timestamp < cutoff:
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
        device_clock_mode: str = "utc",
    ) -> None:
        cutoff = (
            self._overlap_cutoff(
                table="hrv_samples",
                device_id=device_id,
                target_day=target,
                interval_minutes=max(1, history.range_minutes),
            )
            if device_clock_mode == "utc"
            else None
        )
        rows = []
        for sample_index, (value, timestamp) in enumerate(history.readings_with_times(target, clock_mode=device_clock_mode)):
            if value == 0:
                continue
            if cutoff is not None and timestamp < cutoff:
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
