from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from ..schemas import DataQualityResponse
from ..time import utc_day_from_iso
from .common import ResolvedDevice, latest_metric_day, time_context
from .device_status import device_status_payload


def data_quality_payload(conn: sqlite3.Connection, resolved: ResolvedDevice) -> DataQualityResponse:
    device_id = int(resolved.row["device_id"])
    report_date = latest_metric_day(conn, device_id)
    start_iso, end_iso = utc_day_from_iso(report_date)
    previous_start, _ = utc_day_from_iso((date.fromisoformat(report_date) - timedelta(days=1)).isoformat())
    counts = {
        "heart_rate": int(conn.execute("SELECT COUNT(*) FROM analytic_heart_rate_intervals WHERE device_id=? AND valid_from>=? AND valid_from<?", (device_id, start_iso, end_iso)).fetchone()[0]),
        "activity": int(conn.execute("SELECT COUNT(*) FROM analytic_activity_intervals WHERE device_id=? AND valid_from>=? AND valid_from<?", (device_id, start_iso, end_iso)).fetchone()[0]),
        "spo2": int(conn.execute("SELECT COUNT(*) FROM analytic_blood_oxygen_intervals WHERE device_id=? AND valid_from>=? AND valid_from<?", (device_id, start_iso, end_iso)).fetchone()[0]),
        "blood_pressure": int(conn.execute("SELECT COUNT(*) FROM analytic_blood_pressure_intervals WHERE device_id=? AND valid_from>=? AND valid_from<?", (device_id, start_iso, end_iso)).fetchone()[0]),
        "stress": int(conn.execute("SELECT COUNT(*) FROM analytic_pressure_intervals WHERE device_id=? AND valid_from>=? AND valid_from<?", (device_id, start_iso, end_iso)).fetchone()[0]),
        "hrv": int(conn.execute("SELECT COUNT(*) FROM analytic_hrv_intervals WHERE device_id=? AND valid_from>=? AND valid_from<?", (device_id, start_iso, end_iso)).fetchone()[0]),
    }
    sleep_present = conn.execute(
        """
        SELECT COUNT(*)
        FROM analytic_daily_sleep
        WHERE device_id=? AND valid_from IN (?, ?)
        """,
        (device_id, start_iso, previous_start),
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
        time_context=time_context(),
    )
