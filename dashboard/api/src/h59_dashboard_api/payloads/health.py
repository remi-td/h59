from __future__ import annotations

import sqlite3

from ..schemas import HealthResponse
from .common import time_context


def health_payload(conn: sqlite3.Connection, db_path: str) -> HealthResponse:
    row = conn.execute("SELECT COUNT(*) AS device_count FROM devices").fetchone()
    device_count = int(row["device_count"]) if row else 0
    status = "ok" if device_count else "empty_database"
    return HealthResponse(status=status, db_path=db_path, device_count=device_count, time_context=time_context())
