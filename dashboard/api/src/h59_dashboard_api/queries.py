from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from statistics import mean
from typing import Any

from .db import utc_now
from .schemas import (
    DataQualityResponse,
    DebugResponse,
    DeviceStatusResponse,
    MetricBreakdownItem,
    DeviceSummary,
    FreshnessClass,
    HealthResponse,
    MetricCard,
    MetricPoint,
    MetricSeriesResponse,
    MetricSummary,
    SleepResponse,
    SleepSessionSummary,
    SleepStageSegment,
    TodayResponse,
)


TRUST_MAP = {
    "steps": "derived",
    "heart-rate": "measured",
    "spo2": "derived",
    "hrv": "derived",
    "stress": "vendor_score",
    "blood-pressure": "estimated",
    "sleep": "derived",
    "battery": "measured",
    "sync": "unknown",
}

RANGE_MAP = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "90d": timedelta(days=90),
}


@dataclass(frozen=True)
class ResolvedDevice:
    row: sqlite3.Row
    battery_percent: int | None
    battery_charging: bool | None
    last_sync: str | None
    freshness: FreshnessClass


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _iso_date(dt: datetime | None) -> str | None:
    return dt.astimezone(UTC).date().isoformat() if dt else None


def _fmt_minutes(minutes: int | None) -> str | None:
    if minutes is None:
        return None
    hours, remainder = divmod(minutes, 60)
    return f"{hours} h {remainder:02d} min"


def _summary(values: list[int | float]) -> MetricSummary | None:
    if not values:
        return None
    return MetricSummary(min=min(values), max=max(values), avg=round(mean(values), 1))


def _quantile(values: list[int | float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    index = (len(ordered) - 1) * fraction
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    weight = index - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def _sparkline_point(
    *,
    timestamp: str,
    value: int | float | None = None,
    min_value: int | float | None = None,
    max_value: int | float | None = None,
    lower_quartile: int | float | None = None,
    median_value: int | float | None = None,
    upper_quartile: int | float | None = None,
    label: str | None = None,
) -> MetricPoint:
    return MetricPoint(
        timestamp=timestamp,
        value=value,
        min_value=min_value,
        max_value=max_value,
        lower_quartile=lower_quartile,
        median_value=median_value,
        upper_quartile=upper_quartile,
        label=label,
    )


def _daily_bucket_timestamps(end_date: date, days: int = 7) -> list[str]:
    start_date = end_date - timedelta(days=days - 1)
    return [
        datetime.combine(start_date + timedelta(days=offset), datetime.min.time(), tzinfo=UTC).isoformat()
        for offset in range(days)
    ]


def _range_start(range_name: str, now: datetime | None = None) -> datetime:
    now = now or utc_now()
    delta = RANGE_MAP.get(range_name, RANGE_MAP["30d"])
    return now - delta


def _freshness_from_sync(last_sync: datetime | None) -> FreshnessClass:
    if last_sync is None:
        return "empty"
    age_minutes = (utc_now() - last_sync).total_seconds() / 60
    if age_minutes <= 60:
        return "fresh"
    if age_minutes <= 360:
        return "partial"
    return "stale"


def _latest_day(conn: sqlite3.Connection, device_id: int) -> str:
    row = conn.execute(
        """
        SELECT MAX(day_value) AS latest_day
        FROM (
            SELECT date(timestamp) AS day_value FROM heart_rates WHERE device_id=?
            UNION ALL
            SELECT date(timestamp) AS day_value FROM sport_details WHERE device_id=?
            UNION ALL
            SELECT date(timestamp) AS day_value FROM blood_oxygen_samples WHERE device_id=?
            UNION ALL
            SELECT date(timestamp) AS day_value FROM pressure_samples WHERE device_id=?
            UNION ALL
            SELECT date(timestamp) AS day_value FROM hrv_samples WHERE device_id=?
            UNION ALL
            SELECT date(COALESCE(end_timestamp, start_timestamp)) AS day_value FROM sleep_sessions WHERE device_id=?
        )
        """,
        (device_id, device_id, device_id, device_id, device_id, device_id),
    ).fetchone()
    if row and row["latest_day"]:
        return str(row["latest_day"])
    return utc_now().date().isoformat()


def _latest_sync(conn: sqlite3.Connection, device_id: int) -> str | None:
    row = conn.execute(
        "SELECT MAX(finished_at) AS finished_at FROM syncs WHERE device_id=? AND finished_at IS NOT NULL",
        (device_id,),
    ).fetchone()
    return row["finished_at"] if row else None


def _latest_battery(conn: sqlite3.Connection, device_id: int) -> tuple[int | None, bool | None]:
    row = conn.execute(
        """
        SELECT battery_level, charging
        FROM battery_samples
        WHERE device_id=?
        ORDER BY timestamp DESC
        LIMIT 1
        """,
        (device_id,),
    ).fetchone()
    if row is None:
        return None, None
    return int(row["battery_level"]), bool(row["charging"])


def resolve_device_summary(conn: sqlite3.Connection, row: sqlite3.Row, *, is_preferred: bool) -> ResolvedDevice:
    last_sync_raw = _latest_sync(conn, int(row["device_id"]))
    battery_percent, battery_charging = _latest_battery(conn, int(row["device_id"]))
    last_sync_dt = _parse_iso(last_sync_raw)
    return ResolvedDevice(
        row=row,
        battery_percent=battery_percent,
        battery_charging=battery_charging,
        last_sync=last_sync_raw,
        freshness=_freshness_from_sync(last_sync_dt),
    )


def device_summary_payload(resolved: ResolvedDevice, *, is_preferred: bool) -> DeviceSummary:
    row = resolved.row
    return DeviceSummary(
        id=int(row["device_id"]),
        nickname=row["nickname"],
        name=row["name"],
        address=row["address"],
        battery_percent=resolved.battery_percent,
        last_sync=resolved.last_sync,
        data_freshness=resolved.freshness,
        is_preferred=is_preferred,
    )


def health_payload(conn: sqlite3.Connection, db_path: str) -> HealthResponse:
    row = conn.execute("SELECT COUNT(*) AS device_count FROM devices").fetchone()
    device_count = int(row["device_count"]) if row else 0
    status = "ok" if device_count else "empty_database"
    return HealthResponse(status=status, db_path=db_path, device_count=device_count)


def devices_payload(conn: sqlite3.Connection, preferred_id: int | None) -> list[DeviceSummary]:
    rows = conn.execute(
        """
        SELECT *
        FROM devices
        ORDER BY
            CASE WHEN last_seen_at IS NULL THEN 1 ELSE 0 END,
            last_seen_at DESC,
            device_id ASC
        """
    ).fetchall()
    return [
        device_summary_payload(
            resolve_device_summary(conn, row, is_preferred=int(row["device_id"]) == preferred_id),
            is_preferred=int(row["device_id"]) == preferred_id,
        )
        for row in rows
    ]


def today_payload(conn: sqlite3.Connection, resolved: ResolvedDevice, *, is_preferred: bool) -> TodayResponse:
    device_id = int(resolved.row["device_id"])
    report_date = utc_now().date().isoformat()
    heart_rows = conn.execute(
        """
        SELECT reading, timestamp
        FROM heart_rates
        WHERE device_id=? AND date(timestamp)=?
        ORDER BY timestamp ASC
        """,
        (device_id, report_date),
    ).fetchall()
    sport_rows = conn.execute(
        """
        SELECT steps, distance, calories, timestamp
        FROM sport_details
        WHERE device_id=? AND date(timestamp)=?
        ORDER BY timestamp ASC
        """,
        (device_id, report_date),
    ).fetchall()
    latest_sleep = conn.execute(
        """
        SELECT *
        FROM sleep_sessions
        WHERE device_id=? AND date(COALESCE(end_timestamp, start_timestamp))=?
        ORDER BY COALESCE(end_timestamp, start_timestamp) DESC
        LIMIT 1
        """,
        (device_id, report_date),
    ).fetchone()
    latest_spo2 = conn.execute(
        """
        SELECT min_percent, max_percent, timestamp
        FROM blood_oxygen_samples
        WHERE device_id=? AND date(timestamp)=?
        ORDER BY timestamp DESC
        LIMIT 1
        """,
        (device_id, report_date),
    ).fetchone()
    latest_hrv = conn.execute(
        """
        SELECT value, timestamp
        FROM hrv_samples
        WHERE device_id=? AND date(timestamp)=?
        ORDER BY timestamp DESC
        LIMIT 1
        """,
        (device_id, report_date),
    ).fetchone()
    latest_pressure = conn.execute(
        """
        SELECT value, timestamp
        FROM pressure_samples
        WHERE device_id=? AND date(timestamp)=?
        ORDER BY timestamp DESC
        LIMIT 1
        """,
        (device_id, report_date),
    ).fetchone()
    spo2_rows = conn.execute(
        """
        SELECT min_percent, max_percent, timestamp
        FROM blood_oxygen_samples
        WHERE device_id=? AND date(timestamp)=?
        ORDER BY timestamp ASC
        """,
        (device_id, report_date),
    ).fetchall()
    hrv_rows = conn.execute(
        """
        SELECT value, timestamp
        FROM hrv_samples
        WHERE device_id=? AND date(timestamp)=?
        ORDER BY timestamp ASC
        """,
        (device_id, report_date),
    ).fetchall()
    pressure_rows = conn.execute(
        """
        SELECT value, timestamp
        FROM pressure_samples
        WHERE device_id=? AND date(timestamp)=?
        ORDER BY timestamp ASC
        """,
        (device_id, report_date),
    ).fetchall()
    battery_rows = conn.execute(
        """
        SELECT battery_level, timestamp
        FROM battery_samples
        WHERE device_id=? AND date(timestamp)=?
        ORDER BY timestamp ASC
        """,
        (device_id, report_date),
    ).fetchall()
    sleep_breakdown: list[MetricBreakdownItem] = []
    if latest_sleep is not None:
        stage_rows = conn.execute(
            """
            SELECT stage, SUM(minutes) AS minutes_total
            FROM sleep_stage_samples
            WHERE sleep_session_id=?
            GROUP BY stage
            ORDER BY minutes_total DESC, stage ASC
            """,
            (int(latest_sleep["sleep_session_id"]),),
        ).fetchall()
        sleep_breakdown = [
            MetricBreakdownItem(label=str(row["stage"]), value=int(row["minutes_total"]))
            for row in stage_rows
            if row["minutes_total"] is not None
        ]

    hr_values = [int(row["reading"]) for row in heart_rows]
    step_values = [int(row["steps"]) for row in sport_rows]
    steps_total = sum(step_values)
    latest_hr = hr_values[-1] if hr_values else None

    running_steps = 0
    recent_steps = []
    for row in sport_rows:
        running_steps += int(row["steps"])
        recent_steps.append(_sparkline_point(timestamp=str(row["timestamp"]), value=running_steps))
    recent_heart = [
        _sparkline_point(timestamp=str(row["timestamp"]), value=int(row["reading"]))
        for row in heart_rows
    ]
    recent_spo2 = [
        _sparkline_point(
            timestamp=str(row["timestamp"]),
            value=round((int(row["min_percent"]) + int(row["max_percent"])) / 2, 1),
            min_value=int(row["min_percent"]),
            max_value=int(row["max_percent"]),
        )
        for row in spo2_rows
    ]
    recent_hrv = [
        _sparkline_point(timestamp=str(row["timestamp"]), value=int(row["value"]))
        for row in hrv_rows
    ]
    recent_pressure = [
        _sparkline_point(timestamp=str(row["timestamp"]), value=int(row["value"]))
        for row in pressure_rows
    ]
    recent_battery = [
        _sparkline_point(timestamp=str(row["timestamp"]), value=int(row["battery_level"]))
        for row in battery_rows
    ]
    latest_battery = int(battery_rows[-1]["battery_level"]) if battery_rows else None

    cards = [
        MetricCard(
            id="steps",
            title="Steps",
            value=steps_total if sport_rows else None,
            unit="steps",
            trust_class="derived",
            status=resolved.freshness if sport_rows else "empty",
            subtitle=(f"{len(sport_rows)} stored activity summaries" if sport_rows else "No activity summaries"),
            trend_type="line",
            sparkline=recent_steps,
        ),
        MetricCard(
            id="heart_rate",
            title="Heart Rate",
            value=latest_hr,
            unit="bpm",
            trust_class="measured",
            status=resolved.freshness if hr_values else "empty",
            summary=_summary(hr_values),
            subtitle=None,
            trend_type="line",
            sparkline=recent_heart,
        ),
        MetricCard(
            id="sleep",
            title="Sleep",
            value=int(latest_sleep["total_minutes"]) if latest_sleep and latest_sleep["total_minutes"] is not None else None,
            unit="minutes",
            display_value=_fmt_minutes(int(latest_sleep["total_minutes"])) if latest_sleep and latest_sleep["total_minutes"] is not None else None,
            trust_class="derived",
            status=resolved.freshness if latest_sleep else "empty",
            subtitle=f"{latest_sleep['start_timestamp']} -> {latest_sleep['end_timestamp']}" if latest_sleep else "No sleep session",
            trend_type="none",
            sparkline=[],
            breakdown=sleep_breakdown,
        ),
        MetricCard(
            id="spo2",
            title="Blood Oxygen",
            value=round((int(latest_spo2["min_percent"]) + int(latest_spo2["max_percent"])) / 2, 1) if latest_spo2 else None,
            unit="%",
            trust_class="derived",
            status=resolved.freshness if latest_spo2 else "empty",
            summary=MetricSummary(
                min=float(latest_spo2["min_percent"]),
                max=float(latest_spo2["max_percent"]),
                avg=round((int(latest_spo2["min_percent"]) + int(latest_spo2["max_percent"])) / 2, 1),
            ) if latest_spo2 else None,
            trend_type="line",
            sparkline=recent_spo2,
        ),
        MetricCard(
            id="hrv",
            title="HRV",
            value=int(latest_hrv["value"]) if latest_hrv else None,
            unit="ms",
            trust_class="derived",
            status=resolved.freshness if latest_hrv else "empty",
            trend_type="line",
            sparkline=recent_hrv,
        ),
        MetricCard(
            id="stress",
            title="Stress",
            value=int(latest_pressure["value"]) if latest_pressure else None,
            unit=None,
            trust_class="vendor_score",
            status=resolved.freshness if latest_pressure else "empty",
            trend_type="line",
            sparkline=recent_pressure,
        ),
        MetricCard(
            id="blood_pressure",
            title="Blood Pressure Estimate",
            value=None,
            unit="mmHg",
            trust_class="estimated",
            status="empty",
            subtitle="Not currently captured from local H59 history",
            trend_type="none",
        ),
        MetricCard(
            id="battery",
            title="Battery",
            value=latest_battery,
            unit="%",
            trust_class="measured",
            status=resolved.freshness if latest_battery is not None else "empty",
            trend_type="line",
            sparkline=recent_battery,
        ),
    ]

    return TodayResponse(
        date=report_date,
        device=device_summary_payload(resolved, is_preferred=is_preferred),
        cards=cards,
    )


def metric_series_payload(conn: sqlite3.Connection, device_id: int, metric: str, range_name: str) -> MetricSeriesResponse:
    start = _range_start(range_name)
    start_iso = start.isoformat()
    if metric == "heart-rate" and range_name == "7d":
        rows = conn.execute(
            """
            SELECT date(timestamp) AS day_value, reading
            FROM heart_rates
            WHERE device_id=? AND timestamp>=?
            ORDER BY timestamp ASC
            """,
            (device_id, start_iso),
        ).fetchall()
        buckets: dict[str, list[int]] = {}
        for row in rows:
            buckets.setdefault(str(row["day_value"]), []).append(int(row["reading"]))
        points = [
            MetricPoint(
                timestamp=f"{day_value}T00:00:00+00:00",
                value=_quantile(values, 0.5),
                min_value=min(values),
                max_value=max(values),
                lower_quartile=_quantile(values, 0.25),
                median_value=_quantile(values, 0.5),
                upper_quartile=_quantile(values, 0.75),
            )
            for day_value, values in sorted(buckets.items())
            if values
        ]
        flat_values = [value for values in buckets.values() for value in values]
        return MetricSeriesResponse(
            metric=metric,
            label="Heart Rate",
            unit="bpm",
            trust_class="measured",
            range=range_name,
            available=bool(points),
            points=points,
            latest_value=points[-1].median_value if points else None,
            summary=_summary([float(v) for v in flat_values]) if flat_values else None,
        )
    if metric == "blood-pressure":
        return MetricSeriesResponse(
            metric=metric,
            label="Blood Pressure Estimate",
            unit="mmHg",
            trust_class="estimated",
            range=range_name,
            available=False,
            note="Historical blood-pressure extraction is not currently proven for this device.",
        )

    configs: dict[str, dict[str, Any]] = {
        "heart-rate": {
            "table": "heart_rates",
            "value": "reading",
            "label": "Heart Rate",
            "unit": "bpm",
            "trust": "measured",
            "point_builder": lambda row: MetricPoint(timestamp=row["timestamp"], value=int(row["reading"])),
        },
        "hrv": {
            "table": "hrv_samples",
            "value": "value",
            "label": "HRV",
            "unit": "ms",
            "trust": "derived",
            "point_builder": lambda row: MetricPoint(timestamp=row["timestamp"], value=int(row["value"])),
        },
        "stress": {
            "table": "pressure_samples",
            "value": "value",
            "label": "Stress",
            "unit": None,
            "trust": "vendor_score",
            "point_builder": lambda row: MetricPoint(timestamp=row["timestamp"], value=int(row["value"])),
        },
        "spo2": {
            "table": "blood_oxygen_samples",
            "value": "max_percent",
            "label": "Blood Oxygen",
            "unit": "%",
            "trust": "derived",
            "point_builder": lambda row: MetricPoint(
                timestamp=row["timestamp"],
                value=round((int(row["min_percent"]) + int(row["max_percent"])) / 2, 1),
                min_value=int(row["min_percent"]),
                max_value=int(row["max_percent"]),
            ),
        },
        "steps": {
            "table": "sport_details",
            "value": "steps",
            "label": "Steps",
            "unit": "steps",
            "trust": "derived",
        },
    }
    if metric not in configs:
        raise KeyError(metric)
    config = configs[metric]
    if metric == "steps":
        rows = conn.execute(
            """
            SELECT date(timestamp) AS day_value, SUM(steps) AS steps_total
            FROM sport_details
            WHERE device_id=? AND timestamp>=?
            GROUP BY day_value
            ORDER BY day_value ASC
            """,
            (device_id, start_iso),
        ).fetchall()
        points = [MetricPoint(timestamp=f"{row['day_value']}T00:00:00+00:00", value=int(row["steps_total"])) for row in rows]
        values = [int(row["steps_total"]) for row in rows]
    elif metric == "spo2":
        rows = conn.execute(
            """
            SELECT timestamp, min_percent, max_percent
            FROM blood_oxygen_samples
            WHERE device_id=? AND timestamp>=?
            ORDER BY timestamp ASC
            """,
            (device_id, start_iso),
        ).fetchall()
        points = [config["point_builder"](row) for row in rows]
        values = [point.value for point in points if point.value is not None]
    else:
        rows = conn.execute(
            f"""
            SELECT timestamp, {config['value']}
            FROM {config['table']}
            WHERE device_id=? AND timestamp>=?
            ORDER BY timestamp ASC
            """,
            (device_id, start_iso),
        ).fetchall()
        points = [config["point_builder"](row) for row in rows]
        values = [point.value for point in points if point.value is not None]
    return MetricSeriesResponse(
        metric=metric,
        label=config["label"],
        unit=config["unit"],
        trust_class=config["trust"],
        range=range_name,
        available=bool(points),
        points=points,
        latest_value=values[-1] if values else None,
        summary=_summary([float(v) for v in values]) if values else None,
    )


def sleep_payload(conn: sqlite3.Connection, device_id: int, range_name: str) -> SleepResponse:
    start = _range_start(range_name).isoformat()
    rows = conn.execute(
        """
        SELECT *
        FROM sleep_sessions
        WHERE device_id=? AND COALESCE(end_timestamp, start_timestamp)>=?
        ORDER BY COALESCE(end_timestamp, start_timestamp) DESC
        """,
        (device_id, start),
    ).fetchall()
    sessions: list[SleepSessionSummary] = []
    for row in rows:
        stages = conn.execute(
            """
            SELECT stage, start_timestamp, end_timestamp, minutes, is_provisional
            FROM sleep_stage_samples
            WHERE sleep_session_id=?
            ORDER BY sequence_index ASC
            """,
            (int(row["sleep_session_id"]),),
        ).fetchall()
        sessions.append(
            SleepSessionSummary(
                start_timestamp=row["start_timestamp"],
                end_timestamp=row["end_timestamp"],
                total_minutes=int(row["total_minutes"]) if row["total_minutes"] is not None else None,
                state=row["state"],
                score=float(row["score"]) if row["score"] is not None else None,
                is_provisional=bool(row["is_provisional"]),
                stages=[
                    SleepStageSegment(
                        stage=stage["stage"],
                        start_timestamp=stage["start_timestamp"],
                        end_timestamp=stage["end_timestamp"],
                        minutes=int(stage["minutes"]),
                        is_provisional=bool(stage["is_provisional"]),
                    )
                    for stage in stages
                ],
            )
        )
    daily_totals = [
        MetricPoint(timestamp=f"{row['sleep_day']}T00:00:00+00:00", value=int(row["minutes_total"]))
        for row in conn.execute(
            """
            SELECT date(COALESCE(end_timestamp, start_timestamp)) AS sleep_day, SUM(total_minutes) AS minutes_total
            FROM sleep_sessions
            WHERE device_id=? AND COALESCE(end_timestamp, start_timestamp)>=?
            GROUP BY sleep_day
            ORDER BY sleep_day ASC
            """,
            (device_id, start),
        ).fetchall()
    ]
    return SleepResponse(
        range=range_name,
        available=bool(sessions),
        sessions=sessions,
        latest_session=sessions[0] if sessions else None,
        daily_totals=daily_totals,
    )


def device_status_payload(conn: sqlite3.Connection, resolved: ResolvedDevice, *, is_preferred: bool) -> DeviceStatusResponse:
    device_id = int(resolved.row["device_id"])
    latest_samples = {}
    for metric, query in {
        "heart_rate": "SELECT MAX(timestamp) AS value FROM heart_rates WHERE device_id=?",
        "activity": "SELECT MAX(timestamp) AS value FROM sport_details WHERE device_id=?",
        "sleep": "SELECT MAX(end_timestamp) AS value FROM sleep_sessions WHERE device_id=?",
        "spo2": "SELECT MAX(timestamp) AS value FROM blood_oxygen_samples WHERE device_id=?",
        "stress": "SELECT MAX(timestamp) AS value FROM pressure_samples WHERE device_id=?",
        "hrv": "SELECT MAX(timestamp) AS value FROM hrv_samples WHERE device_id=?",
    }.items():
        row = conn.execute(query, (device_id,)).fetchone()
        latest_samples[metric] = row["value"] if row else None
    last_sample = max((value for value in latest_samples.values() if value), default=None)
    return DeviceStatusResponse(
        device=device_summary_payload(resolved, is_preferred=is_preferred),
        battery_charging=resolved.battery_charging,
        last_sample_timestamp=last_sample,
        latest_samples=latest_samples,
    )


def data_quality_payload(conn: sqlite3.Connection, resolved: ResolvedDevice) -> DataQualityResponse:
    device_id = int(resolved.row["device_id"])
    report_date = _latest_day(conn, device_id)
    counts = {
        "heart_rate": int(conn.execute("SELECT COUNT(*) FROM heart_rates WHERE device_id=? AND date(timestamp)=?", (device_id, report_date)).fetchone()[0]),
        "activity": int(conn.execute("SELECT COUNT(*) FROM sport_details WHERE device_id=? AND date(timestamp)=?", (device_id, report_date)).fetchone()[0]),
        "spo2": int(conn.execute("SELECT COUNT(*) FROM blood_oxygen_samples WHERE device_id=? AND date(timestamp)=?", (device_id, report_date)).fetchone()[0]),
        "stress": int(conn.execute("SELECT COUNT(*) FROM pressure_samples WHERE device_id=? AND date(timestamp)=?", (device_id, report_date)).fetchone()[0]),
        "hrv": int(conn.execute("SELECT COUNT(*) FROM hrv_samples WHERE device_id=? AND date(timestamp)=?", (device_id, report_date)).fetchone()[0]),
    }
    sleep_present = conn.execute(
        "SELECT COUNT(*) FROM sleep_sessions WHERE device_id=? AND date(COALESCE(end_timestamp, start_timestamp)) IN (?, ?)",
        (
            device_id,
            report_date,
            (date.fromisoformat(report_date) - timedelta(days=1)).isoformat(),
        ),
    ).fetchone()[0] > 0
    latest_samples = device_status_payload(conn, resolved, is_preferred=True).latest_samples
    missing = [metric for metric, count in counts.items() if count == 0]
    if not sleep_present:
        missing.append("sleep")
    return DataQualityResponse(
        device_id=device_id,
        status=resolved.freshness,
        last_successful_sync=resolved.last_sync,
        sample_counts_today=counts,
        latest_sample_timestamps=latest_samples,
        sleep_record_present=sleep_present,
        missing_metrics=missing,
    )


def debug_payload(conn: sqlite3.Connection, resolved: ResolvedDevice, *, is_preferred: bool) -> DebugResponse:
    device_id = int(resolved.row["device_id"])
    table_counts = {}
    for table in [
        "heart_rates",
        "sport_details",
        "sleep_sessions",
        "sleep_stage_samples",
        "blood_oxygen_samples",
        "pressure_samples",
        "hrv_samples",
        "battery_samples",
        "raw_packets",
    ]:
        query = f"SELECT COUNT(*) FROM {table} WHERE device_id=?"
        table_counts[table] = int(conn.execute(query, (device_id,)).fetchone()[0])
    recent_syncs = [
        {
            "sync_id": int(row["sync_id"]),
            "started_at": row["timestamp"],
            "finished_at": row["finished_at"],
            "source": row["source"],
        }
        for row in conn.execute(
            """
            SELECT sync_id, timestamp, finished_at, source
            FROM syncs
            WHERE device_id=?
            ORDER BY timestamp DESC
            LIMIT 20
            """,
            (device_id,),
        ).fetchall()
    ]
    return DebugResponse(
        device=device_summary_payload(resolved, is_preferred=is_preferred),
        table_counts=table_counts,
        recent_syncs=recent_syncs,
    )
