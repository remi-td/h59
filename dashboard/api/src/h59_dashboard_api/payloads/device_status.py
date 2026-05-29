from __future__ import annotations

import sqlite3

from ..schemas import DeviceStatusResponse
from .common import ResolvedDevice, device_summary_payload, time_context


def device_status_payload(conn: sqlite3.Connection, resolved: ResolvedDevice, *, is_preferred: bool) -> DeviceStatusResponse:
    device_id = int(resolved.row["device_id"])
    latest_samples = {}
    for metric, query in {
        "heart_rate": "SELECT MAX(valid_from) AS value FROM analytic_heart_rate_intervals WHERE device_id=?",
        "activity": "SELECT MAX(valid_from) AS value FROM analytic_activity_intervals WHERE device_id=?",
        "sleep": "SELECT MAX(valid_to) AS value FROM analytic_sleep_stage_intervals WHERE device_id=?",
        "spo2": "SELECT MAX(valid_from) AS value FROM analytic_blood_oxygen_intervals WHERE device_id=?",
        "stress": "SELECT MAX(valid_from) AS value FROM analytic_pressure_intervals WHERE device_id=?",
        "hrv": "SELECT MAX(valid_from) AS value FROM analytic_hrv_intervals WHERE device_id=?",
    }.items():
        row = conn.execute(query, (device_id,)).fetchone()
        latest_samples[metric] = row["value"] if row else None
    last_sample = max((value for value in latest_samples.values() if value), default=None)
    return DeviceStatusResponse(
        device=device_summary_payload(resolved, is_preferred=is_preferred),
        battery_charging=resolved.battery_charging,
        last_sample_timestamp=last_sample,
        latest_samples=latest_samples,
        time_context=time_context(),
    )
