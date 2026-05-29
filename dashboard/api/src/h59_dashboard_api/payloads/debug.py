from __future__ import annotations

import sqlite3

from ..schemas import DebugResponse
from .common import ResolvedDevice, device_summary_payload


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
