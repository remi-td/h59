from __future__ import annotations

import sqlite3

from .common import device_summary_payload, resolve_device_summary


def devices_payload(conn: sqlite3.Connection, preferred_id: int | None) -> list:
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
