"""Date and time helpers for H59 syncing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Iterator


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def start_of_day(ts: datetime) -> datetime:
    return ts.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def end_of_day(ts: datetime) -> datetime:
    return start_of_day(ts) + timedelta(days=1, microseconds=-1)


def dates_between(start: datetime, end: datetime) -> Iterator[datetime]:
    """Yield one UTC date anchor per day, inclusive."""
    start_day = start_of_day(start)
    end_day = start_of_day(end)
    if end_day < start_day:
        raise ValueError("start is after end")

    day = start_day
    while day <= end_day:
        yield day
        day += timedelta(days=1)


def minutes_so_far(ts: datetime) -> int:
    """Return the approximate number of minutes elapsed in the UTC day plus one."""
    dt = ts.astimezone(UTC)
    midnight = datetime(dt.year, dt.month, dt.day, tzinfo=UTC)
    delta = dt - midnight
    return round(delta.total_seconds() / 60) + 1


def is_today(ts: datetime) -> bool:
    dt = ts.astimezone(UTC)
    now = utc_now()
    return (dt.year, dt.month, dt.day) == (now.year, now.month, now.day)
