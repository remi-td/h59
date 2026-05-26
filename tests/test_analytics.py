import sqlite3
import os
import datetime
from h59_client import analytics


def _open_db():
    path = os.path.join(os.getcwd(), "data", "h59.sqlite")
    if os.path.exists(path):
        return sqlite3.connect(path)
    # create a small in-memory DB with expected schema
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """CREATE TABLE sport_details(
            sport_detail_id INTEGER PRIMARY KEY,
            calories INTEGER,
            steps INTEGER,
            distance INTEGER,
            timestamp TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE heart_rates(
            heart_rate_id INTEGER PRIMARY KEY,
            reading INTEGER,
            timestamp TEXT
        )"""
    )
    # insert sample data for 2026-05-24
    conn.executemany(
        "INSERT INTO sport_details(calories,steps,distance,timestamp) VALUES (?,?,?,?)",
        [
            (100, 1000, 700, "2026-05-24 10:00:00"),
            (200, 2000, 1400, "2026-05-24 12:00:00"),
        ],
    )
    conn.executemany(
        "INSERT INTO heart_rates(reading,timestamp) VALUES (?,?)",
        [
            (60, "2026-05-24 10:01:00"),
            (70, "2026-05-24 10:05:00"),
            (80, "2026-05-24 12:10:00"),
        ],
    )
    conn.commit()
    return conn


def test_compute_daily_summary_returns_expected_keys():
    conn = _open_db()
    s = analytics.compute_daily_summary(conn, "2026-05-24")
    assert s["date"] == "2026-05-24"
    assert "steps" in s and "calories" in s and "distance_meters" in s
    assert "hr_avg" in s and "hr_count" in s


def test_heart_rate_time_series_order():
    conn = _open_db()
    ts = analytics.heart_rate_time_series(conn, "2026-05-24")
    assert len(ts) >= 1
    # timestamps should be increasing
    stamps = [t["timestamp"] for t in ts]
    assert stamps == sorted(stamps)
