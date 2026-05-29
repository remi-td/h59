from __future__ import annotations

import sqlite3
from datetime import UTC

from ..db import utc_now
from ..schemas import MetricBreakdownItem, MetricCard, MetricSummary, TodayResponse
from ..time import utc_day_bounds
from .common import ResolvedDevice, device_summary_payload, fmt_minutes, sparkline_point, summary, time_context


def today_payload(conn: sqlite3.Connection, resolved: ResolvedDevice, *, is_preferred: bool) -> TodayResponse:
    device_id = int(resolved.row["device_id"])
    report_day = utc_now().astimezone(UTC).date()
    report_date = report_day.isoformat()
    start_iso, end_iso = utc_day_bounds(report_day)

    heart_rows = conn.execute(
        """
        SELECT value AS reading, valid_from
        FROM analytic_heart_rate_intervals
        WHERE device_id=? AND valid_from>=? AND valid_from<?
        ORDER BY valid_from ASC
        """,
        (device_id, start_iso, end_iso),
    ).fetchall()
    sport_rows = conn.execute(
        """
        SELECT steps, distance, calories, valid_from
        FROM analytic_activity_intervals
        WHERE device_id=? AND valid_from>=? AND valid_from<?
        ORDER BY valid_from ASC
        """,
        (device_id, start_iso, end_iso),
    ).fetchall()
    latest_sleep = conn.execute(
        """
        SELECT *
        FROM analytic_sleep_sessions_canonical
        WHERE device_id=? AND end_timestamp>=? AND end_timestamp<?
        ORDER BY end_timestamp DESC
        LIMIT 1
        """,
        (device_id, start_iso, end_iso),
    ).fetchone()
    latest_spo2 = conn.execute(
        """
        SELECT min_percent, max_percent, valid_from
        FROM analytic_blood_oxygen_intervals
        WHERE device_id=? AND valid_from>=? AND valid_from<?
        ORDER BY valid_from DESC
        LIMIT 1
        """,
        (device_id, start_iso, end_iso),
    ).fetchone()
    latest_hrv = conn.execute(
        """
        SELECT value, valid_from
        FROM analytic_hrv_intervals
        WHERE device_id=? AND valid_from>=? AND valid_from<?
        ORDER BY valid_from DESC
        LIMIT 1
        """,
        (device_id, start_iso, end_iso),
    ).fetchone()
    latest_pressure = conn.execute(
        """
        SELECT value, valid_from
        FROM analytic_pressure_intervals
        WHERE device_id=? AND valid_from>=? AND valid_from<?
        ORDER BY valid_from DESC
        LIMIT 1
        """,
        (device_id, start_iso, end_iso),
    ).fetchone()
    spo2_rows = conn.execute(
        """
        SELECT min_percent, max_percent, valid_from
        FROM analytic_blood_oxygen_intervals
        WHERE device_id=? AND valid_from>=? AND valid_from<?
        ORDER BY valid_from ASC
        """,
        (device_id, start_iso, end_iso),
    ).fetchall()
    hrv_rows = conn.execute(
        """
        SELECT value, valid_from
        FROM analytic_hrv_intervals
        WHERE device_id=? AND valid_from>=? AND valid_from<?
        ORDER BY valid_from ASC
        """,
        (device_id, start_iso, end_iso),
    ).fetchall()
    pressure_rows = conn.execute(
        """
        SELECT value, valid_from
        FROM analytic_pressure_intervals
        WHERE device_id=? AND valid_from>=? AND valid_from<?
        ORDER BY valid_from ASC
        """,
        (device_id, start_iso, end_iso),
    ).fetchall()
    battery_rows = conn.execute(
        """
        SELECT battery_level, timestamp
        FROM battery_samples
        WHERE device_id=? AND timestamp>=? AND timestamp<?
        ORDER BY timestamp ASC
        """,
        (device_id, start_iso, end_iso),
    ).fetchall()

    sleep_breakdown: list[MetricBreakdownItem] = []
    if latest_sleep is not None:
        stage_rows = conn.execute(
            """
            SELECT stage, SUM(minutes) AS minutes_total
            FROM analytic_sleep_stage_intervals
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
        recent_steps.append(sparkline_point(timestamp=str(row["valid_from"]), value=running_steps))

    recent_heart = [sparkline_point(timestamp=str(row["valid_from"]), value=int(row["reading"])) for row in heart_rows]
    recent_spo2 = [
        sparkline_point(
            timestamp=str(row["valid_from"]),
            value=round((int(row["min_percent"]) + int(row["max_percent"])) / 2, 1),
            min_value=int(row["min_percent"]),
            max_value=int(row["max_percent"]),
        )
        for row in spo2_rows
    ]
    recent_hrv = [sparkline_point(timestamp=str(row["valid_from"]), value=int(row["value"])) for row in hrv_rows]
    recent_pressure = [sparkline_point(timestamp=str(row["valid_from"]), value=int(row["value"])) for row in pressure_rows]
    recent_battery = [sparkline_point(timestamp=str(row["timestamp"]), value=int(row["battery_level"])) for row in battery_rows]
    latest_battery = int(battery_rows[-1]["battery_level"]) if battery_rows else None

    cards = [
        MetricCard(
            id="steps",
            title="Steps",
            value=steps_total if sport_rows else None,
            unit="steps",
            trust_class="derived",
            status=resolved.freshness if sport_rows else "empty",
            subtitle=f"{len(sport_rows)} stored activity summaries" if sport_rows else "No activity summaries",
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
            summary=summary(hr_values),
            subtitle=None,
            trend_type="line",
            sparkline=recent_heart,
        ),
        MetricCard(
            id="sleep",
            title="Sleep",
            value=int(latest_sleep["total_minutes"]) if latest_sleep and latest_sleep["total_minutes"] is not None else None,
            unit="minutes",
            display_value=fmt_minutes(int(latest_sleep["total_minutes"])) if latest_sleep and latest_sleep["total_minutes"] is not None else None,
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
        time_context=time_context(),
        device=device_summary_payload(resolved, is_preferred=is_preferred),
        cards=cards,
    )
