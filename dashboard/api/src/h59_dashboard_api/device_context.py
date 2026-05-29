from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from fastapi import HTTPException

from .db import resolve_device
from .payloads.common import ResolvedDevice, resolve_device_summary


@dataclass(frozen=True)
class DeviceContext:
    resolved: ResolvedDevice
    is_preferred: bool


def preferred_device_id(conn: sqlite3.Connection) -> int | None:
    preferred = resolve_device(conn, "preferred")
    if preferred is None:
        return None
    return int(preferred["device_id"])


def require_device_context(conn: sqlite3.Connection, selector: str) -> DeviceContext:
    row = resolve_device(conn, selector)
    if row is None:
        raise HTTPException(status_code=404, detail=f"device not found for selector: {selector}")
    preferred_id = preferred_device_id(conn)
    is_preferred = preferred_id is not None and preferred_id == int(row["device_id"])
    return DeviceContext(
        resolved=resolve_device_summary(conn, row, is_preferred=is_preferred),
        is_preferred=is_preferred,
    )
