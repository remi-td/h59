from __future__ import annotations

import sqlite3

from ..schemas import MetricPoint, SleepResponse, SleepSessionSummary, SleepStageSegment
from ..time import range_start
from .common import time_context


def sleep_payload(conn: sqlite3.Connection, device_id: int, range_name: str) -> SleepResponse:
    start = range_start(range_name).isoformat()
    rows = conn.execute(
        """
        SELECT *
        FROM analytic_sleep_sessions_canonical
        WHERE device_id=? AND end_timestamp>=?
        ORDER BY end_timestamp DESC
        """,
        (device_id, start),
    ).fetchall()
    sessions: list[SleepSessionSummary] = []
    for row in rows:
        stages = conn.execute(
            """
            SELECT stage, valid_from, valid_to, minutes, is_provisional
            FROM analytic_sleep_stage_intervals
            WHERE sleep_session_id=?
            ORDER BY valid_from ASC
            """,
            (int(row["sleep_session_id"]),),
        ).fetchall()
        sessions.append(
            SleepSessionSummary(
                start_timestamp=row["start_timestamp"],
                end_timestamp=row["end_timestamp"],
                total_minutes=int(row["total_minutes"]) if row["total_minutes"] is not None else None,
                state=row["state"],
                score=float(row["score"]) if row["score"] is not None else None,
                is_provisional=bool(row["is_provisional"]),
                stages=[
                    SleepStageSegment(
                        stage=stage["stage"],
                        start_timestamp=stage["valid_from"],
                        end_timestamp=stage["valid_to"],
                        minutes=int(stage["minutes"]),
                        is_provisional=bool(stage["is_provisional"]),
                    )
                    for stage in stages
                ],
            )
        )
    daily_totals = [
        MetricPoint(timestamp=row["valid_from"], value=int(row["minutes_total"]))
        for row in conn.execute(
            """
            SELECT valid_from, minutes_total
            FROM analytic_daily_sleep
            WHERE device_id=? AND valid_from>=?
            ORDER BY valid_from ASC
            """,
            (device_id, start),
        ).fetchall()
    ]
    return SleepResponse(
        range=range_name,
        available=bool(sessions),
        sessions=sessions,
        latest_session=sessions[0] if sessions else None,
        daily_totals=daily_totals,
        time_context=time_context(),
    )
