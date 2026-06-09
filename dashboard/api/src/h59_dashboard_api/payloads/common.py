from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from statistics import mean

from h59_client.analytics import ensure_analytic_views

from ..db import utc_now
from ..schemas import DeviceSummary, FreshnessClass, MetricPoint, MetricSummary, TimeContext


@dataclass(frozen=True)
class ResolvedDevice:
    row: sqlite3.Row
    battery_percent: int | None
    battery_charging: bool | None
    last_sync: str | None
    freshness: FreshnessClass


REQUIRED_ANALYTIC_VIEWS = {
    "analytic_heart_rate_intervals",
    "analytic_activity_intervals",
    "analytic_sleep_stage_intervals",
    "analytic_sleep_sessions_classified",
    "analytic_sleep_sessions_canonical",
    "analytic_blood_oxygen_intervals",
    "analytic_blood_pressure_intervals",
    "analytic_pressure_intervals",
    "analytic_hrv_intervals",
    "analytic_daily_steps",
    "analytic_daily_sleep",
    "health_daily_features",
    "health_metric_observations",
    "health_metric_baselines",
    "health_feature_observations",
    "health_daily_feature_store",
    "health_feature_baselines",
}

# View names alone are not enough: analytic view definitions evolve over time,
# and existing SQLite DBs keep the old CREATE VIEW SQL until we explicitly rebuild
# them.  Validate the columns consumed by the dashboard before deciding that the
# analytic surface is current.
REQUIRED_ANALYTIC_VIEW_COLUMNS = {
    "analytic_sleep_sessions_canonical": {"effective_minutes"},
    "health_daily_features": {"observation_as_of", "sleep_effective_minutes", "systolic_bp_latest", "diastolic_bp_latest"},
    "health_feature_observations": {"feature_name", "feature_value", "confidence", "observation_as_of", "approximation_label"},
    "health_daily_feature_store": {"sleep_efficiency_pct", "strain_score_0_21", "data_quality_state"},
    "health_feature_baselines": {"sample_count", "median", "mean_abs_deviation", "baseline_status"},
}


def _analytic_surface_is_current(conn: sqlite3.Connection, existing: set[str]) -> bool:
    if not REQUIRED_ANALYTIC_VIEWS.issubset(existing):
        return False
    for view_name, required_columns in REQUIRED_ANALYTIC_VIEW_COLUMNS.items():
        columns = {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({view_name})").fetchall()}
        if not required_columns.issubset(columns):
            return False
    return True


def ensure_analytic_surface(conn: sqlite3.Connection) -> None:
    existing = {
        str(row["name"])
        for row in conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='view'
            """
        ).fetchall()
    }
    if _analytic_surface_is_current(conn, existing):
        return
    try:
        ensure_analytic_views(conn)
    except sqlite3.OperationalError as exc:
        if "readonly" not in str(exc).lower() and "read-only" not in str(exc).lower():
            raise
        db_row = conn.execute("PRAGMA database_list").fetchone()
        db_path = db_row["file"] if db_row is not None else None
        if not db_path:
            raise
        with sqlite3.connect(str(db_path)) as writable_conn:
            writable_conn.row_factory = sqlite3.Row
            ensure_analytic_views(writable_conn)
            writable_conn.commit()


def fmt_minutes(minutes: int | None) -> str | None:
    if minutes is None:
        return None
    hours, remainder = divmod(minutes, 60)
    return f"{hours} h {remainder:02d} min"


def summary(values: list[int | float]) -> MetricSummary | None:
    if not values:
        return None
    return MetricSummary(min=min(values), max=max(values), avg=round(mean(values), 1))


def quantile(values: list[int | float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    index = (len(ordered) - 1) * fraction
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    weight = index - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def sparkline_point(
    *,
    timestamp: str,
    value: int | float | None = None,
    min_value: int | float | None = None,
    max_value: int | float | None = None,
    lower_quartile: int | float | None = None,
    median_value: int | float | None = None,
    upper_quartile: int | float | None = None,
    label: str | None = None,
) -> MetricPoint:
    return MetricPoint(
        timestamp=timestamp,
        value=value,
        min_value=min_value,
        max_value=max_value,
        lower_quartile=lower_quartile,
        median_value=median_value,
        upper_quartile=upper_quartile,
        label=label,
    )


def freshness_from_sync(last_sync: datetime | None) -> FreshnessClass:
    if last_sync is None:
        return "empty"
    age_minutes = (utc_now() - last_sync).total_seconds() / 60
    if age_minutes <= 60:
        return "fresh"
    if age_minutes <= 360:
        return "partial"
    return "stale"


def latest_sync(conn: sqlite3.Connection, device_id: int) -> str | None:
    row = conn.execute(
        "SELECT MAX(finished_at) AS finished_at FROM syncs WHERE device_id=? AND finished_at IS NOT NULL",
        (device_id,),
    ).fetchone()
    return row["finished_at"] if row else None


def latest_battery(conn: sqlite3.Connection, device_id: int) -> tuple[int | None, bool | None]:
    row = conn.execute(
        """
        SELECT battery_level, charging
        FROM battery_samples
        WHERE device_id=?
        ORDER BY timestamp DESC
        LIMIT 1
        """,
        (device_id,),
    ).fetchone()
    if row is None:
        return None, None
    return int(row["battery_level"]), bool(row["charging"])


def resolve_device_summary(conn: sqlite3.Connection, row: sqlite3.Row, *, is_preferred: bool) -> ResolvedDevice:
    last_sync_raw = latest_sync(conn, int(row["device_id"]))
    battery_percent, battery_charging = latest_battery(conn, int(row["device_id"]))
    last_sync_dt = datetime.fromisoformat(last_sync_raw) if last_sync_raw else None
    return ResolvedDevice(
        row=row,
        battery_percent=battery_percent,
        battery_charging=battery_charging,
        last_sync=last_sync_raw,
        freshness=freshness_from_sync(last_sync_dt),
    )


def device_summary_payload(resolved: ResolvedDevice, *, is_preferred: bool) -> DeviceSummary:
    row = resolved.row
    return DeviceSummary(
        id=int(row["device_id"]),
        nickname=row["nickname"],
        name=row["name"],
        address=row["address"],
        battery_percent=resolved.battery_percent,
        last_sync=resolved.last_sync,
        data_freshness=resolved.freshness,
        is_preferred=is_preferred,
    )


def latest_metric_day(conn: sqlite3.Connection, device_id: int) -> str:
    row = conn.execute(
        """
        SELECT MAX(day_value) AS latest_day
        FROM (
            SELECT date(valid_from) AS day_value FROM analytic_heart_rate_intervals WHERE device_id=?
            UNION ALL
            SELECT day_value FROM analytic_daily_steps WHERE device_id=?
            UNION ALL
            SELECT date(valid_from) AS day_value FROM analytic_blood_oxygen_intervals WHERE device_id=?
            UNION ALL
            SELECT date(valid_from) AS day_value FROM analytic_blood_pressure_intervals WHERE device_id=?
            UNION ALL
            SELECT date(valid_from) AS day_value FROM analytic_pressure_intervals WHERE device_id=?
            UNION ALL
            SELECT date(valid_from) AS day_value FROM analytic_hrv_intervals WHERE device_id=?
            UNION ALL
            SELECT sleep_day AS day_value FROM analytic_daily_sleep WHERE device_id=?
        )
        """,
        (device_id, device_id, device_id, device_id, device_id, device_id, device_id),
    ).fetchone()
    if row and row["latest_day"]:
        return str(row["latest_day"])
    return utc_now().date().isoformat()


def daily_bucket_timestamps(end_date: date, days: int = 7) -> list[str]:
    start_date = end_date - timedelta(days=days - 1)
    return [
        datetime.combine(start_date + timedelta(days=offset), datetime.min.time(), tzinfo=UTC).isoformat()
        for offset in range(days)
    ]


def time_context() -> TimeContext:
    return TimeContext()
