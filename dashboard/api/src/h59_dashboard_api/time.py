from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from .db import utc_now


RANGE_MAP = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "90d": timedelta(days=90),
}


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def iso_date(value: datetime | None) -> str | None:
    return value.astimezone(UTC).date().isoformat() if value else None


def utc_day_bounds(day_value: date) -> tuple[str, str]:
    start = datetime.combine(day_value, datetime.min.time(), tzinfo=UTC)
    end = start + timedelta(days=1)
    return start.isoformat(), end.isoformat()


def utc_day_from_iso(day_text: str) -> tuple[str, str]:
    return utc_day_bounds(date.fromisoformat(day_text))


def range_start(range_name: str, now: datetime | None = None) -> datetime:
    now = now or utc_now()
    return now - RANGE_MAP.get(range_name, RANGE_MAP["30d"])
