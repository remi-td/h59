"""Date and time helpers for H59 syncing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Iterator


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def local_now() -> datetime:
    return datetime.now().astimezone()


def start_of_day(ts: datetime) -> datetime:
    return ts.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def start_of_clock_day(ts: datetime, mode: str) -> datetime:
    if mode == "utc":
        return start_of_day(ts)
    if mode == "local":
        return ts.astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    raise ValueError(f"unsupported device clock mode: {mode}")


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


def dates_between_clock(start: datetime, end: datetime, mode: str) -> Iterator[datetime]:
    start_day = start_of_clock_day(start, mode)
    end_day = start_of_clock_day(end, mode)
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


def minutes_so_far_clock(ts: datetime, mode: str) -> int:
    if mode == "utc":
        return minutes_so_far(ts)
    if mode == "local":
        dt = ts.astimezone()
        midnight = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        delta = dt - midnight
        return round(delta.total_seconds() / 60) + 1
    raise ValueError(f"unsupported device clock mode: {mode}")


def is_today(ts: datetime) -> bool:
    dt = ts.astimezone(UTC)
    now = utc_now()
    return (dt.year, dt.month, dt.day) == (now.year, now.month, now.day)


def is_today_clock(ts: datetime, mode: str) -> bool:
    if mode == "utc":
        return is_today(ts)
    if mode == "local":
        dt = ts.astimezone()
        now = local_now()
        return (dt.year, dt.month, dt.day) == (now.year, now.month, now.day)
    raise ValueError(f"unsupported device clock mode: {mode}")
