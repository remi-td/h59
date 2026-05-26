"""Simple analytics helpers for H59 data stored in SQLite.

This module provides small, well-tested functions to compute daily
summaries (steps, calories, HR stats) and to return time-series for
heart-rate samples. Functions accept an sqlite3.Connection so they
are easy to unit-test against a real H59 SQLite database or an
in-memory test database.
"""
from typing import Dict, List, Any
import datetime


def _to_date_str(date) -> str:
    if isinstance(date, str):
        return date
    if isinstance(date, datetime.date):
        return date.isoformat()
    if isinstance(date, datetime.datetime):
        return date.date().isoformat()
    raise TypeError("date must be str or datetime.date/datetime")


def compute_daily_summary(conn, date) -> Dict[str, Any]:
    """Compute a daily summary for `date` (YYYY-MM-DD or date).

    Returns dict with keys: date, steps, calories, distance_meters,
    hr_count, hr_avg, hr_min, hr_max.
    """
    ds = _to_date_str(date)
    cur = conn.cursor()

    # aggregate sport details
    cur.execute(
        """SELECT COALESCE(SUM(steps),0), COALESCE(SUM(calories),0), COALESCE(SUM(distance),0)
           FROM sport_details
           WHERE date(timestamp)=?""",
        (ds,),
    )
    steps, calories, distance = cur.fetchone()

    # heart rate stats
    cur.execute(
        """SELECT COUNT(reading),
                    COALESCE(AVG(reading),0),
                    COALESCE(MIN(reading),0),
                    COALESCE(MAX(reading),0)
           FROM heart_rates
           WHERE date(timestamp)=?""",
        (ds,),
    )
    hr_count, hr_avg, hr_min, hr_max = cur.fetchone()

    return {
        "date": ds,
        "steps": int(steps),
        "calories": int(calories),
        "distance_meters": float(distance),
        "hr_count": int(hr_count),
        "hr_avg": float(hr_avg) if hr_count else None,
        "hr_min": int(hr_min) if hr_count else None,
        "hr_max": int(hr_max) if hr_count else None,
    }


def heart_rate_time_series(conn, date) -> List[Dict[str, Any]]:
    """Return list of {timestamp, reading} for the given date ordered by time."""
    ds = _to_date_str(date)
    cur = conn.cursor()
    cur.execute(
        """SELECT timestamp, reading FROM heart_rates
           WHERE date(timestamp)=?
           ORDER BY timestamp ASC""",
        (ds,),
    )
    rows = cur.fetchall()
    return [{"timestamp": r[0], "reading": int(r[1])} for r in rows]
