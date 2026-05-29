from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

from .config import Settings


def utc_now() -> datetime:
    return datetime.now(UTC)


def _sqlite_uri(path: Path, *, read_only: bool) -> tuple[str, bool]:
    if read_only:
        return f"file:{path}?mode=ro", True
    return str(path), False


@contextmanager
def connect(settings: Settings) -> Iterator[sqlite3.Connection]:
    path = settings.db_path
    if not path.exists():
        raise FileNotFoundError(f"database does not exist: {path}")
    target, use_uri = _sqlite_uri(path, read_only=settings.read_only)
    conn = sqlite3.connect(target, uri=use_uri)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def resolve_device(conn: sqlite3.Connection, selector: str | None) -> sqlite3.Row | None:
    if selector in {None, "", "preferred"}:
        return conn.execute(
            """
            SELECT *
            FROM devices
            ORDER BY
                CASE WHEN last_seen_at IS NULL THEN 1 ELSE 0 END,
                last_seen_at DESC,
                device_id ASC
            LIMIT 1
            """
        ).fetchone()

    if selector.isdigit():
        row = conn.execute("SELECT * FROM devices WHERE device_id=?", (int(selector),)).fetchone()
        if row is not None:
            return row

    for column in ("nickname", "address", "name"):
        row = conn.execute(f"SELECT * FROM devices WHERE {column}=?", (selector,)).fetchone()
        if row is not None:
            return row
    return None
