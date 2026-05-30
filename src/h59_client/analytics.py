"""Analytic helpers and SQLite views for H59 data.

The device-facing storage layer preserves raw and minimally typed data.
This module defines the logical analytic layer that projects that device data
into stable consumer-oriented shapes.
"""

from __future__ import annotations

import datetime
import sqlite3
from typing import Any


ANALYTIC_VIEWS_SQL = """
DROP VIEW IF EXISTS analytic_heart_rate_intervals;
DROP VIEW IF EXISTS analytic_activity_intervals;
DROP VIEW IF EXISTS analytic_sleep_stage_intervals;
DROP VIEW IF EXISTS analytic_blood_oxygen_intervals;
DROP VIEW IF EXISTS analytic_blood_pressure_intervals;
DROP VIEW IF EXISTS analytic_pressure_intervals;
DROP VIEW IF EXISTS analytic_hrv_intervals;
DROP VIEW IF EXISTS analytic_daily_steps;
DROP VIEW IF EXISTS analytic_daily_sleep;
DROP VIEW IF EXISTS analytic_sleep_sessions_canonical;

CREATE VIEW IF NOT EXISTS analytic_heart_rate_intervals AS
SELECT
    hr.heart_rate_id AS source_id,
    hr.device_id,
    hr.sync_id,
    hr.timestamp AS valid_from,
    strftime(
        '%Y-%m-%dT%H:%M:%S+00:00',
        unixepoch(hr.timestamp) + (
            COALESCE(
                (
                    SELECT hrs.interval_minutes
                    FROM heart_rate_settings AS hrs
                    WHERE hrs.device_id = hr.device_id
                    ORDER BY hrs.timestamp DESC
                    LIMIT 1
                ),
                5
            ) * 60
        ),
        'unixepoch'
    ) AS valid_to,
    hr.reading AS value,
    hr.source_command,
    hr.raw_packet_hex
FROM heart_rates AS hr;

CREATE VIEW IF NOT EXISTS analytic_activity_intervals AS
SELECT
    sd.sport_detail_id AS source_id,
    sd.device_id,
    sd.sync_id,
    sd.timestamp AS valid_from,
    strftime('%Y-%m-%dT%H:%M:%S+00:00', unixepoch(sd.timestamp) + (60 * 60), 'unixepoch') AS valid_to,
    sd.steps,
    sd.distance,
    sd.calories,
    sd.time_index,
    sd.source_command,
    sd.raw_packet_hex
FROM sport_details AS sd;

CREATE VIEW IF NOT EXISTS analytic_sleep_stage_intervals AS
SELECT
    sss.sleep_stage_sample_id AS source_id,
    sss.sleep_session_id,
    sss.device_id,
    sss.sync_id,
    sss.stage,
    sss.start_timestamp AS valid_from,
    sss.end_timestamp AS valid_to,
    sss.minutes,
    sss.is_provisional,
    sss.raw_json
FROM sleep_stage_samples AS sss;

CREATE VIEW IF NOT EXISTS analytic_sleep_sessions_canonical AS
WITH sleep_quality AS (
    SELECT
        ss.sleep_session_id,
        ss.device_id,
        ss.sync_id,
        ss.start_timestamp,
        ss.end_timestamp,
        ss.total_minutes,
        ss.state,
        ss.score,
        ss.is_provisional,
        ss.source_command,
        ss.raw_json,
        date(COALESCE(ss.end_timestamp, ss.start_timestamp)) AS sleep_day,
        COALESCE(SUM(CASE WHEN sss.stage = 'no-data' THEN sss.minutes ELSE 0 END), 0) AS no_data_minutes
    FROM sleep_sessions AS ss
    LEFT JOIN sleep_stage_samples AS sss
      ON sss.sleep_session_id = ss.sleep_session_id
    GROUP BY ss.sleep_session_id
),
ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY device_id, sleep_day
            ORDER BY
                no_data_minutes ASC,
                end_timestamp DESC,
                total_minutes DESC,
                sleep_session_id DESC
        ) AS session_rank
    FROM sleep_quality
)
SELECT
    sleep_session_id,
    device_id,
    sync_id,
    start_timestamp,
    end_timestamp,
    total_minutes,
    state,
    score,
    is_provisional,
    source_command,
    raw_json,
    sleep_day,
    no_data_minutes
FROM ranked
WHERE session_rank = 1;

CREATE VIEW IF NOT EXISTS analytic_blood_oxygen_intervals AS
SELECT
    bos.blood_oxygen_sample_id AS source_id,
    bos.device_id,
    bos.sync_id,
    bos.timestamp AS valid_from,
    strftime('%Y-%m-%dT%H:%M:%S+00:00', unixepoch(bos.timestamp) + (bos.interval_minutes * 60), 'unixepoch') AS valid_to,
    ROUND((bos.min_percent + bos.max_percent) / 2.0, 1) AS value,
    bos.min_percent,
    bos.max_percent,
    bos.interval_minutes,
    bos.is_provisional,
    bos.source_command,
    bos.raw_packet_hex
FROM blood_oxygen_samples AS bos;

CREATE VIEW IF NOT EXISTS analytic_blood_pressure_intervals AS
SELECT
    bpr.blood_pressure_reading_id AS source_id,
    bpr.device_id,
    bpr.sync_id,
    bpr.timestamp AS valid_from,
    strftime('%Y-%m-%dT%H:%M:%S+00:00', unixepoch(bpr.timestamp) + (5 * 60), 'unixepoch') AS valid_to,
    bpr.systolic,
    bpr.diastolic,
    ROUND((bpr.systolic + (2.0 * bpr.diastolic)) / 3.0, 1) AS mean_arterial_pressure,
    bpr.source_command,
    bpr.raw_packet_hex
FROM blood_pressure_readings AS bpr;

CREATE VIEW IF NOT EXISTS analytic_pressure_intervals AS
SELECT
    ps.pressure_sample_id AS source_id,
    ps.device_id,
    ps.sync_id,
    ps.timestamp AS valid_from,
    strftime('%Y-%m-%dT%H:%M:%S+00:00', unixepoch(ps.timestamp) + (ps.interval_minutes * 60), 'unixepoch') AS valid_to,
    ps.value,
    ps.interval_minutes,
    ps.source_command,
    ps.raw_packet_hex
FROM pressure_samples AS ps;

CREATE VIEW IF NOT EXISTS analytic_hrv_intervals AS
SELECT
    hs.hrv_sample_id AS source_id,
    hs.device_id,
    hs.sync_id,
    hs.timestamp AS valid_from,
    strftime('%Y-%m-%dT%H:%M:%S+00:00', unixepoch(hs.timestamp) + (hs.interval_minutes * 60), 'unixepoch') AS valid_to,
    hs.value,
    hs.interval_minutes,
    hs.source_command,
    hs.raw_packet_hex
FROM hrv_samples AS hs;

CREATE VIEW IF NOT EXISTS analytic_daily_steps AS
SELECT
    device_id,
    date(timestamp) AS day_value,
    strftime('%Y-%m-%dT00:00:00+00:00', timestamp) AS valid_from,
    strftime('%Y-%m-%dT00:00:00+00:00', unixepoch(timestamp) + (24 * 60 * 60), 'unixepoch') AS valid_to,
    SUM(steps) AS steps_total,
    SUM(distance) AS distance_total,
    SUM(calories) AS calories_total,
    COUNT(*) AS sample_count
FROM sport_details
GROUP BY device_id, date(timestamp);

CREATE VIEW IF NOT EXISTS analytic_daily_sleep AS
SELECT
    device_id,
    sleep_day,
    strftime('%Y-%m-%dT00:00:00+00:00', end_timestamp) AS valid_from,
    strftime('%Y-%m-%dT00:00:00+00:00', unixepoch(end_timestamp) + (24 * 60 * 60), 'unixepoch') AS valid_to,
    SUM(total_minutes) AS minutes_total,
    COUNT(*) AS session_count
FROM analytic_sleep_sessions_canonical
GROUP BY device_id, sleep_day;
"""


def ensure_analytic_views(conn: sqlite3.Connection) -> None:
    """Create the logical analytic surface over device-owned tables."""
    conn.executescript(ANALYTIC_VIEWS_SQL)


def _to_date_str(date_value: str | datetime.date | datetime.datetime) -> str:
    if isinstance(date_value, str):
        return date_value
    if isinstance(date_value, datetime.date):
        return date_value.isoformat()
    if isinstance(date_value, datetime.datetime):
        return date_value.date().isoformat()
    raise TypeError("date must be str or datetime.date/datetime")


def _utc_day_bounds(date_value: str | datetime.date | datetime.datetime) -> tuple[str, str]:
    day = datetime.date.fromisoformat(_to_date_str(date_value))
    start = datetime.datetime.combine(day, datetime.time.min, tzinfo=datetime.UTC)
    end = start + datetime.timedelta(days=1)
    return start.isoformat(), end.isoformat()


def compute_daily_summary(conn: sqlite3.Connection, date_value: str | datetime.date | datetime.datetime) -> dict[str, Any]:
    """Compute a daily summary for a UTC day using explicit range predicates."""
    start_iso, end_iso = _utc_day_bounds(date_value)
    day_value = _to_date_str(date_value)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT COALESCE(SUM(steps), 0), COALESCE(SUM(calories), 0), COALESCE(SUM(distance), 0)
        FROM sport_details
        WHERE replace(timestamp, ' ', 'T') >= ? AND replace(timestamp, ' ', 'T') < ?
        """,
        (start_iso, end_iso),
    )
    steps, calories, distance = cur.fetchone()

    cur.execute(
        """
        SELECT
            COUNT(reading),
            COALESCE(AVG(reading), 0),
            COALESCE(MIN(reading), 0),
            COALESCE(MAX(reading), 0)
        FROM heart_rates
        WHERE replace(timestamp, ' ', 'T') >= ? AND replace(timestamp, ' ', 'T') < ?
        """,
        (start_iso, end_iso),
    )
    hr_count, hr_avg, hr_min, hr_max = cur.fetchone()

    return {
        "date": day_value,
        "steps": int(steps),
        "calories": int(calories),
        "distance_meters": float(distance),
        "hr_count": int(hr_count),
        "hr_avg": float(hr_avg) if hr_count else None,
        "hr_min": int(hr_min) if hr_count else None,
        "hr_max": int(hr_max) if hr_count else None,
    }


def heart_rate_time_series(conn: sqlite3.Connection, date_value: str | datetime.date | datetime.datetime) -> list[dict[str, Any]]:
    """Return [{timestamp, reading}] for the given UTC day ordered by time."""
    start_iso, end_iso = _utc_day_bounds(date_value)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT timestamp, reading
        FROM heart_rates
        WHERE replace(timestamp, ' ', 'T') >= ? AND replace(timestamp, ' ', 'T') < ?
        ORDER BY timestamp ASC
        """,
        (start_iso, end_iso),
    )
    rows = cur.fetchall()
    return [{"timestamp": row[0], "reading": int(row[1])} for row in rows]
