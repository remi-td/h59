"""Markdown coverage report for the H59 health dashboard requirements."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


METRIC_LABELS = {
    "blood-pressure": "Blood pressure estimate",
    "blood-sugar": "Blood sugar",
    "ecg": "ECG",
    "fatigue": "Fatigue",
    "health-check": "One key measurement",
    "heart-rate": "Heart rate",
    "hrv": "HRV",
    "pressure": "Pressure / stress-like",
    "spo2": "SpO2",
}


@dataclass
class ReportContext:
    db_path: Path
    generated_at: datetime
    device_id: int
    device_name: str | None
    device_address: str
    report_date: str


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _fmt_ts(value: str | None) -> str:
    if not value:
        return "n/a"
    dt = _parse_iso(value)
    if dt is None:
        return "n/a"
    return dt.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def _fmt_minutes(value: int | None) -> str:
    if value is None:
        return "n/a"
    hours, minutes = divmod(value, 60)
    return f"{hours:02d} h {minutes:02d} min"


def _device_row(conn: sqlite3.Connection, device_id: int | None = None) -> sqlite3.Row:
    if device_id is not None:
        row = conn.execute("SELECT * FROM devices WHERE device_id=?", (device_id,)).fetchone()
        if row is None:
            raise ValueError(f"device_id {device_id} not found")
        return row

    row = conn.execute(
        """
        SELECT *
        FROM devices
        ORDER BY
            CASE WHEN last_seen_at IS NULL THEN 1 ELSE 0 END,
            last_seen_at DESC,
            device_id DESC
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        raise ValueError("database does not contain any device")
    return row


def _latest_report_date(conn: sqlite3.Connection, device_id: int) -> str:
    row = conn.execute(
        """
        SELECT MAX(day_value) AS latest_day
        FROM (
            SELECT date(timestamp) AS day_value FROM heart_rates WHERE device_id=?
            UNION ALL
            SELECT date(timestamp) AS day_value FROM sport_details WHERE device_id=?
            UNION ALL
            SELECT date(COALESCE(end_timestamp, start_timestamp)) AS day_value FROM sleep_sessions WHERE device_id=?
            UNION ALL
            SELECT date(timestamp) AS day_value FROM battery_samples WHERE device_id=?
            UNION ALL
            SELECT date(timestamp) AS day_value FROM syncs WHERE device_id=?
        )
        """,
        (device_id, device_id, device_id, device_id, device_id),
    ).fetchone()
    latest_day = row["latest_day"] if row is not None else None
    if latest_day:
        return str(latest_day)
    return datetime.now(UTC).date().isoformat()


def _latest_capabilities(conn: sqlite3.Connection, device_id: int) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT capabilities_json
        FROM capability_snapshots
        WHERE device_id=?
        ORDER BY timestamp DESC
        LIMIT 1
        """,
        (device_id,),
    ).fetchone()
    if row is None or not row["capabilities_json"]:
        return {}
    return json.loads(row["capabilities_json"])


def _daily_steps(conn: sqlite3.Connection, device_id: int, report_date: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS block_count,
            COALESCE(SUM(steps), 0) AS steps_total,
            COALESCE(SUM(distance), 0) AS distance_total,
            COALESCE(SUM(calories), 0) AS calories_total,
            MIN(timestamp) AS first_block,
            MAX(timestamp) AS last_block
        FROM sport_details
        WHERE device_id=? AND date(timestamp)=?
        """,
        (device_id, report_date),
    ).fetchone()
    hourly_rows = conn.execute(
        """
        SELECT
            strftime('%H:00', timestamp) AS hour_bucket,
            SUM(steps) AS steps_total
        FROM sport_details
        WHERE device_id=? AND date(timestamp)=?
        GROUP BY hour_bucket
        ORDER BY hour_bucket
        """,
        (device_id, report_date),
    ).fetchall()
    return {
        "block_count": int(row["block_count"]),
        "steps_total": int(row["steps_total"]),
        "distance_total": int(row["distance_total"]),
        "calories_total": int(row["calories_total"]),
        "first_block": row["first_block"],
        "last_block": row["last_block"],
        "hourly_steps": [(hour_row["hour_bucket"], int(hour_row["steps_total"])) for hour_row in hourly_rows],
    }


def _daily_heart_rate(conn: sqlite3.Connection, device_id: int, report_date: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS sample_count,
            COALESCE(AVG(reading), 0) AS avg_reading,
            COALESCE(MIN(reading), 0) AS min_reading,
            COALESCE(MAX(reading), 0) AS max_reading,
            MIN(timestamp) AS first_sample,
            MAX(timestamp) AS last_sample
        FROM heart_rates
        WHERE device_id=? AND date(timestamp)=?
        """,
        (device_id, report_date),
    ).fetchone()
    latest_row = conn.execute(
        """
        SELECT reading, timestamp
        FROM heart_rates
        WHERE device_id=? AND date(timestamp)=?
        ORDER BY timestamp DESC
        LIMIT 1
        """,
        (device_id, report_date),
    ).fetchone()
    return {
        "sample_count": int(row["sample_count"]),
        "avg_reading": round(float(row["avg_reading"]), 1) if row["sample_count"] else None,
        "min_reading": int(row["min_reading"]) if row["sample_count"] else None,
        "max_reading": int(row["max_reading"]) if row["sample_count"] else None,
        "first_sample": row["first_sample"],
        "last_sample": row["last_sample"],
        "latest_reading": int(latest_row["reading"]) if latest_row else None,
        "latest_timestamp": latest_row["timestamp"] if latest_row else None,
    }


def _sleep_summary(conn: sqlite3.Connection, device_id: int, report_date: str) -> dict[str, Any]:
    total = conn.execute(
        "SELECT COUNT(*) AS count_value FROM sleep_sessions WHERE device_id=?",
        (device_id,),
    ).fetchone()["count_value"]
    daily = conn.execute(
        """
        SELECT COUNT(*) AS count_value
        FROM sleep_sessions
        WHERE device_id=?
          AND (
            date(start_timestamp)=?
            OR date(end_timestamp)=?
          )
        """,
        (device_id, report_date, report_date),
    ).fetchone()["count_value"]
    latest_row = conn.execute(
        """
        SELECT start_timestamp, end_timestamp, state, score
        FROM sleep_sessions
        WHERE device_id=?
        ORDER BY COALESCE(end_timestamp, start_timestamp) DESC
        LIMIT 1
        """,
        (device_id,),
    ).fetchone()
    stage_total = conn.execute(
        """
        SELECT COUNT(*) AS count_value
        FROM sleep_stage_samples
        WHERE device_id=?
        """,
        (device_id,),
    ).fetchone()["count_value"]
    duration_minutes = None
    if latest_row and latest_row["start_timestamp"] and latest_row["end_timestamp"]:
        start_dt = _parse_iso(latest_row["start_timestamp"])
        end_dt = _parse_iso(latest_row["end_timestamp"])
        if start_dt and end_dt:
            duration_minutes = int((end_dt - start_dt).total_seconds() // 60)
    return {
        "total_count": int(total),
        "daily_count": int(daily),
        "latest_start": latest_row["start_timestamp"] if latest_row else None,
        "latest_end": latest_row["end_timestamp"] if latest_row else None,
        "latest_state": latest_row["state"] if latest_row else None,
        "latest_score": latest_row["score"] if latest_row else None,
        "latest_duration_minutes": duration_minutes,
        "stage_total": int(stage_total),
    }


def _historical_metric_counts(conn: sqlite3.Connection, device_id: int, report_date: str) -> dict[str, int]:
    queries = {
        "blood_oxygen_daily": "SELECT COUNT(*) FROM blood_oxygen_samples WHERE device_id=? AND date(timestamp)=?",
        "blood_oxygen_total": "SELECT COUNT(*) FROM blood_oxygen_samples WHERE device_id=?",
        "pressure_daily": "SELECT COUNT(*) FROM pressure_samples WHERE device_id=? AND date(timestamp)=?",
        "pressure_total": "SELECT COUNT(*) FROM pressure_samples WHERE device_id=?",
        "hrv_daily": "SELECT COUNT(*) FROM hrv_samples WHERE device_id=? AND date(timestamp)=?",
        "hrv_total": "SELECT COUNT(*) FROM hrv_samples WHERE device_id=?",
    }
    output: dict[str, int] = {}
    for key, query in queries.items():
        params: tuple[Any, ...] = (device_id, report_date) if "daily" in key else (device_id,)
        output[key] = int(conn.execute(query, params).fetchone()[0])
    return output


def _latest_realtime_by_metric(conn: sqlite3.Connection, device_id: int) -> dict[str, dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT metric, value, error_code, timestamp
        FROM realtime_samples
        WHERE device_id=?
        ORDER BY metric, timestamp DESC
        """,
        (device_id,),
    ).fetchall()
    output: dict[str, dict[str, Any]] = {}
    counts: dict[str, int] = {}
    for row in rows:
        metric = row["metric"]
        counts[metric] = counts.get(metric, 0) + 1
        if metric not in output:
            output[metric] = {
                "value": int(row["value"]),
                "error_code": int(row["error_code"]),
                "timestamp": row["timestamp"],
                "count": 1,
            }
    for metric, count_value in counts.items():
        if metric in output:
            output[metric]["count"] = count_value
    return output


def _sync_summary(conn: sqlite3.Connection, device_id: int) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS total_syncs,
            SUM(CASE WHEN finished_at IS NOT NULL THEN 1 ELSE 0 END) AS completed_syncs,
            SUM(CASE WHEN finished_at IS NULL THEN 1 ELSE 0 END) AS incomplete_syncs,
            MAX(finished_at) AS last_successful_sync,
            MAX(timestamp) AS last_started_sync
        FROM syncs
        WHERE device_id=?
        """,
        (device_id,),
    ).fetchone()
    return {
        "total_syncs": int(row["total_syncs"] or 0),
        "completed_syncs": int(row["completed_syncs"] or 0),
        "incomplete_syncs": int(row["incomplete_syncs"] or 0),
        "last_successful_sync": row["last_successful_sync"],
        "last_started_sync": row["last_started_sync"],
    }


def _battery_summary(conn: sqlite3.Connection, device_id: int) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT battery_level, charging, timestamp
        FROM battery_samples
        WHERE device_id=?
        ORDER BY timestamp DESC
        LIMIT 1
        """,
        (device_id,),
    ).fetchone()
    if row is None:
        return {"battery_level": None, "charging": None, "timestamp": None}
    return {
        "battery_level": int(row["battery_level"]),
        "charging": bool(row["charging"]),
        "timestamp": row["timestamp"],
    }


def _infer_activity_sessions(conn: sqlite3.Connection, device_id: int, report_date: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT timestamp, steps, distance, calories
        FROM sport_details
        WHERE device_id=? AND date(timestamp)=?
          AND (steps > 0 OR distance > 0 OR calories > 0)
        ORDER BY timestamp ASC
        """,
        (device_id, report_date),
    ).fetchall()
    sessions: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    previous_ts: datetime | None = None

    for row in rows:
        timestamp = _parse_iso(row["timestamp"])
        if timestamp is None:
            continue
        if current is None or previous_ts is None or (timestamp - previous_ts) > timedelta(minutes=20):
            if current is not None:
                sessions.append(current)
            current = {
                "start": timestamp,
                "end": timestamp + timedelta(minutes=15),
                "steps": 0,
                "distance": 0,
                "calories": 0,
            }
        current["end"] = timestamp + timedelta(minutes=15)
        current["steps"] += int(row["steps"])
        current["distance"] += int(row["distance"])
        current["calories"] += int(row["calories"])
        previous_ts = timestamp

    if current is not None:
        sessions.append(current)

    for session in sessions:
        hr_row = conn.execute(
            """
            SELECT AVG(reading) AS avg_hr, MIN(reading) AS min_hr, MAX(reading) AS max_hr, COUNT(*) AS sample_count
            FROM heart_rates
            WHERE device_id=? AND timestamp>=? AND timestamp<?
            """,
            (device_id, session["start"].isoformat(), session["end"].isoformat()),
        ).fetchone()
        session["avg_hr"] = round(float(hr_row["avg_hr"]), 1) if hr_row["sample_count"] else None
        session["min_hr"] = int(hr_row["min_hr"]) if hr_row["sample_count"] else None
        session["max_hr"] = int(hr_row["max_hr"]) if hr_row["sample_count"] else None
        session["sample_count"] = int(hr_row["sample_count"])

    return sessions


def _raw_packet_summary(conn: sqlite3.Connection, device_id: int) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT COUNT(*) AS packet_count, MIN(timestamp) AS first_packet, MAX(timestamp) AS last_packet
        FROM raw_packets
        WHERE device_id=?
        """,
        (device_id,),
    ).fetchone()
    return {
        "packet_count": int(row["packet_count"]),
        "first_packet": row["first_packet"],
        "last_packet": row["last_packet"],
    }


def _status_label(condition: bool, partial: bool = False) -> str:
    if condition:
        return "Available"
    if partial:
        return "Partial"
    return "Missing"


def _coverage_rows(
    *,
    capabilities: dict[str, Any],
    steps: dict[str, Any],
    heart_rate: dict[str, Any],
    sleep: dict[str, Any],
    historical_metrics: dict[str, int],
    realtime: dict[str, dict[str, Any]],
    sessions: list[dict[str, Any]],
    battery: dict[str, Any],
    syncs: dict[str, Any],
) -> list[tuple[str, str, str, str, str]]:
    rows: list[tuple[str, str, str, str, str]] = []

    rows.append(
        (
            "Steps",
            _status_label(steps["block_count"] > 0),
            "Daily totals and hourly buckets from 15-minute activity bins",
            "Partial",
            "No raw accelerometer history, no goal logic, calories unit still unvalidated",
        )
    )
    rows.append(
        (
            "Heart rate",
            _status_label(heart_rate["sample_count"] > 0),
            "Latest/min/max/avg from historical 5-minute samples",
            "Available",
            "No night-time segmentation or confidence scoring yet",
        )
    )

    sleep_data = sleep["total_count"] > 0
    rows.append(
        (
            "Sleep",
            _status_label(sleep_data, partial=False),
            "No decoded sleep sessions in current database" if not sleep_data else "Sleep sessions and staged periods available",
            "Missing" if not sleep_data else "Available",
            "Stage semantics still provisional for some values; local-day presentation rules are still missing",
        )
    )

    spo2_supported = bool(capabilities.get("support_spo2"))
    spo2_data = historical_metrics["blood_oxygen_total"] > 0 or "spo2" in realtime
    rows.append(
        (
            "Blood oxygen / SpO2",
            _status_label(spo2_data, partial=spo2_supported),
            (
                f"Historical min/max samples available ({historical_metrics['blood_oxygen_daily']} for selected day)"
                if historical_metrics["blood_oxygen_total"] > 0
                else ("Realtime samples only" if "spo2" in realtime else ("Device advertises support, but no samples are stored" if spo2_supported else "No capture path proven"))
            ),
            "Missing" if not spo2_data else "Partial",
            "Sample timing and header semantics are still provisional; no night-time minimum rule yet",
        )
    )

    hrv_supported = bool(capabilities.get("support_hrv"))
    hrv_data = historical_metrics["hrv_total"] > 0 or "hrv" in realtime
    rows.append(
        (
            "HRV",
            _status_label(hrv_data, partial=hrv_supported),
            (
                f"Historical samples available ({historical_metrics['hrv_daily']} for selected day)"
                if historical_metrics["hrv_total"] > 0
                else ("Realtime samples only" if "hrv" in realtime else ("Device advertises support, but no samples are stored" if hrv_supported else "No capture path proven"))
            ),
            "Missing" if not hrv_data else "Partial",
            "No baseline logic yet; vendor formula and physiological meaning still need validation",
        )
    )

    stress_data = historical_metrics["pressure_total"] > 0 or "pressure" in realtime or "fatigue" in realtime
    stress_supported = bool(capabilities.get("support_pressure"))
    rows.append(
        (
            "Stress",
            _status_label(stress_data, partial=stress_supported),
            (
                f"Historical pressure/stress-like samples available ({historical_metrics['pressure_daily']} for selected day)"
                if historical_metrics["pressure_total"] > 0
                else ("Pressure/fatigue realtime endpoint only" if stress_data else ("Stress-like capability advertised, but not decoded into dashboard semantics" if stress_supported else "No capture path proven"))
            ),
            "Missing" if not stress_data else "Partial",
            "Need mapping from device metric to stress score and label",
        )
    )

    bp_supported = bool(capabilities.get("support_blood_pressure"))
    bp_data = "blood-pressure" in realtime
    rows.append(
        (
            "Blood pressure estimate",
            _status_label(bp_data, partial=bp_supported),
            "Realtime endpoint only" if bp_data else ("Device advertises support, but no stored observations exist" if bp_supported else "No capture path proven"),
            "Missing" if not bp_data else "Partial",
            "No historical sync path, no systolic/diastolic presentation rules, must remain labelled as estimated",
        )
    )

    rows.append(
        (
            "Sport / activity record",
            _status_label(len(sessions) > 0, partial=steps["block_count"] > 0),
            "Sessions inferred from contiguous activity bins" if sessions else "Only raw activity bins are available",
            "Partial",
            "No explicit sport type, no vendor session boundaries, no dedicated exercise table yet",
        )
    )

    one_key_supported = bool(capabilities.get("support_one_key_check"))
    one_key_data = "health-check" in realtime
    rows.append(
        (
            "One key measurement",
            _status_label(one_key_data, partial=one_key_supported),
            "Realtime endpoint only" if one_key_data else ("Device advertises support, but no decoded observation exists" if one_key_supported else "No capture path proven"),
            "Missing" if not one_key_data else "Partial",
            "Need composite score extraction and component breakdown rules",
        )
    )

    status_data = battery["battery_level"] is not None or syncs["last_successful_sync"] is not None
    rows.append(
        (
            "Device status and sync quality",
            _status_label(status_data),
            "Battery, last sync, sync completion counts, raw packet counts",
            "Partial",
            "No live connected/disconnected state persisted, no sync SLA rules yet",
        )
    )
    return rows


def render_health_dashboard_report(
    db_path: str | Path,
    *,
    report_date: str | None = None,
    device_id: int | None = None,
) -> str:
    db_path = Path(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        device = _device_row(conn, device_id)
        actual_date = report_date or _latest_report_date(conn, int(device["device_id"]))
        ctx = ReportContext(
            db_path=db_path,
            generated_at=datetime.now(UTC),
            device_id=int(device["device_id"]),
            device_name=device["name"],
            device_address=str(device["address"]),
            report_date=actual_date,
        )

        capabilities = _latest_capabilities(conn, ctx.device_id)
        steps = _daily_steps(conn, ctx.device_id, ctx.report_date)
        heart_rate = _daily_heart_rate(conn, ctx.device_id, ctx.report_date)
        sleep = _sleep_summary(conn, ctx.device_id, ctx.report_date)
        historical_metrics = _historical_metric_counts(conn, ctx.device_id, ctx.report_date)
        realtime = _latest_realtime_by_metric(conn, ctx.device_id)
        syncs = _sync_summary(conn, ctx.device_id)
        battery = _battery_summary(conn, ctx.device_id)
        sessions = _infer_activity_sessions(conn, ctx.device_id, ctx.report_date)
        raw_packets = _raw_packet_summary(conn, ctx.device_id)
        coverage = _coverage_rows(
            capabilities=capabilities,
            steps=steps,
            heart_rate=heart_rate,
            sleep=sleep,
            historical_metrics=historical_metrics,
            realtime=realtime,
            sessions=sessions,
            battery=battery,
            syncs=syncs,
        )

        lines: list[str] = []
        lines.append("# H59 Health Dashboard Data Audit")
        lines.append("")
        lines.append(f"- Generated at: {_fmt_ts(ctx.generated_at.isoformat())}")
        lines.append(f"- Database: `{ctx.db_path}`")
        lines.append(f"- Device: `{ctx.device_name or 'unknown'}` (`{ctx.device_address}`)")
        lines.append(f"- Device ID: `{ctx.device_id}`")
        lines.append(f"- Selected day: `{ctx.report_date}`")
        lines.append("- Time basis: UTC day boundaries from the stored timestamps")
        lines.append("")
        lines.append("## Daily Overview")
        lines.append("")
        lines.append(f"- Steps: `{steps['steps_total']}`")
        lines.append(f"- Distance: `{steps['distance_total']}`")
        lines.append(f"- Calories-like field: `{steps['calories_total']}`")
        lines.append(f"- Heart-rate samples: `{heart_rate['sample_count']}`")
        lines.append(f"- Latest heart rate: `{heart_rate['latest_reading'] if heart_rate['latest_reading'] is not None else 'n/a'} bpm`")
        lines.append(f"- Last successful sync: `{_fmt_ts(syncs['last_successful_sync'])}`")
        lines.append(f"- Battery: `{battery['battery_level'] if battery['battery_level'] is not None else 'n/a'}%`")
        lines.append("")
        lines.append("## Coverage Matrix")
        lines.append("")
        lines.append("| Requirement | Data in DB | Current extraction/rule coverage | Remaining gap |")
        lines.append("|---|---|---|---|")
        for metric, data_status, current_state, rule_status, gap in coverage:
            lines.append(f"| {metric} | {data_status} | {rule_status}: {current_state} | {gap} |")
        lines.append("")
        lines.append("## Daily Steps")
        lines.append("")
        lines.append(f"- Activity bins on selected day: `{steps['block_count']}`")
        lines.append(f"- First activity bin: `{_fmt_ts(steps['first_block'])}`")
        lines.append(f"- Last activity bin: `{_fmt_ts(steps['last_block'])}`")
        lines.append("- Notes: steps and distance are usable; the calories-like field still needs unit validation against the app.")
        if steps["hourly_steps"]:
            lines.append("")
            lines.append("| Hour bucket | Steps |")
            lines.append("|---|---|")
            for hour_bucket, step_total in steps["hourly_steps"]:
                lines.append(f"| {hour_bucket} | {step_total} |")
        else:
            lines.append("- No activity bins for the selected day.")
        lines.append("")
        lines.append("## Heart Rate")
        lines.append("")
        lines.append(f"- Sample window: `{_fmt_ts(heart_rate['first_sample'])}` to `{_fmt_ts(heart_rate['last_sample'])}`")
        lines.append(f"- Latest: `{heart_rate['latest_reading'] if heart_rate['latest_reading'] is not None else 'n/a'} bpm` at `{_fmt_ts(heart_rate['latest_timestamp'])}`")
        lines.append(f"- Min / avg / max: `{heart_rate['min_reading'] if heart_rate['min_reading'] is not None else 'n/a'} / {heart_rate['avg_reading'] if heart_rate['avg_reading'] is not None else 'n/a'} / {heart_rate['max_reading'] if heart_rate['max_reading'] is not None else 'n/a'} bpm`")
        lines.append("")
        lines.append("## Sleep")
        lines.append("")
        lines.append(f"- Sleep sessions stored: `{sleep['total_count']}` total, `{sleep['daily_count']}` on selected day")
        if sleep["total_count"]:
            lines.append(f"- Latest session: `{_fmt_ts(sleep['latest_start'])}` to `{_fmt_ts(sleep['latest_end'])}`")
            lines.append(f"- Latest duration: `{_fmt_minutes(sleep['latest_duration_minutes'])}`")
        else:
            lines.append("- No decoded sleep data exists yet. This section requires either protocol decoding or local inference rules.")
        lines.append("")
        lines.append("## Blood Oxygen, HRV, Stress, Blood Pressure, One Key")
        lines.append("")
        if realtime:
            lines.append("| Metric | Latest value | Samples stored | Latest timestamp |")
            lines.append("|---|---|---|---|")
            for metric in sorted(realtime):
                entry = realtime[metric]
                label = METRIC_LABELS.get(metric, metric)
                lines.append(f"| {label} | {entry['value']} | {entry['count']} | {_fmt_ts(entry['timestamp'])} |")
        else:
            lines.append("- No realtime metric samples are stored in this database.")
        if capabilities:
            supported_flags = [key for key, value in sorted(capabilities.items()) if key.startswith("support_") and value]
            lines.append(f"- Device-advertised capability flags: `{', '.join(supported_flags) if supported_flags else 'none'}`")
        else:
            lines.append("- No capability snapshot is stored in this database.")
        lines.append("")
        lines.append("## Sport / Activity Sessions")
        lines.append("")
        if sessions:
            lines.append("| Session start | Session end | Duration | Steps | Distance | Calories-like | Avg HR |")
            lines.append("|---|---|---|---|---|---|---|")
            for session in sessions:
                duration_minutes = int((session["end"] - session["start"]).total_seconds() // 60)
                avg_hr = session["avg_hr"] if session["avg_hr"] is not None else "n/a"
                lines.append(
                    f"| {_fmt_ts(session['start'].isoformat())} | {_fmt_ts(session['end'].isoformat())} | {duration_minutes} min | "
                    f"{session['steps']} | {session['distance']} | {session['calories']} | {avg_hr} |"
                )
            lines.append("- These sessions are inferred from contiguous 15-minute activity bins, not explicit device sport records.")
        else:
            lines.append("- No inferred activity sessions were found for the selected day.")
        lines.append("")
        lines.append("## Device and Sync Status")
        lines.append("")
        lines.append(f"- Battery sample: `{battery['battery_level'] if battery['battery_level'] is not None else 'n/a'}%`, charging=`{battery['charging']}` at `{_fmt_ts(battery['timestamp'])}`")
        lines.append(f"- Sync runs: `{syncs['total_syncs']}` total, `{syncs['completed_syncs']}` completed, `{syncs['incomplete_syncs']}` incomplete")
        lines.append(f"- Last sync start: `{_fmt_ts(syncs['last_started_sync'])}`")
        lines.append(f"- Last successful sync: `{_fmt_ts(syncs['last_successful_sync'])}`")
        lines.append(f"- Raw packets captured: `{raw_packets['packet_count']}` from `{_fmt_ts(raw_packets['first_packet'])}` to `{_fmt_ts(raw_packets['last_packet'])}`")
        if syncs["incomplete_syncs"] > 0:
            lines.append("- Warning: at least one sync session in the database has no `finished_at`, which should be treated as a sync quality issue.")
        lines.append("")
        lines.append("## What Is Still Missing")
        lines.append("")
        lines.append("- No raw accelerometer history is stored. Current activity data is already aggregated into 15-minute bins.")
        if sleep["total_count"] == 0:
            lines.append("- No decoded sleep sessions or sleep stages exist yet.")
        if (
            historical_metrics["blood_oxygen_total"] == 0
            and historical_metrics["hrv_total"] == 0
            and historical_metrics["pressure_total"] == 0
        ):
            lines.append("- No historical SpO2, HRV, or stress-like observations are synced into first-class tables.")
        else:
            lines.append(
                f"- Historical samples are now stored for SpO2=`{historical_metrics['blood_oxygen_total']}`, "
                f"HRV=`{historical_metrics['hrv_total']}`, pressure/stress-like=`{historical_metrics['pressure_total']}`."
            )
        lines.append("- No rule layer exists yet for daily goals, night-time windows, baseline HRV, stress labels, or blood-pressure presentation.")
        lines.append("- Timestamps are still reported against UTC storage days; local-day normalization for dashboard display is not implemented.")
        lines.append("")
        lines.append("## Suggested Next Rules To Implement")
        lines.append("")
        lines.append("1. Normalize report dates into the user timezone before building daily cards.")
        lines.append("2. Normalize UTC storage days into the user timezone before building daily cards.")
        lines.append("3. Validate sleep stage semantics, SpO2 sample timing, and pressure/stress naming against more captures.")
        lines.append("4. Validate the calories field against the vendor app before exposing it as kcal.")
        lines.append("5. Investigate historical blood-pressure extraction and decide whether inferred activity sessions are sufficient for the first sport card.")
        lines.append("")
        return "\n".join(lines)
    finally:
        conn.close()
