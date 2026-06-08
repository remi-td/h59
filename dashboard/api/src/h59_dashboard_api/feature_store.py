from __future__ import annotations

import math
import sqlite3
from dataclasses import asdict, dataclass
from statistics import mean
from typing import Any


@dataclass(frozen=True)
class MetricDefinition:
    metric_key: str
    label: str
    category: str
    unit: str | None
    higher_is_better: bool | None
    normal_range_label: str | None
    source: str
    min_required_days: int
    baseline_supported: bool
    dashboard_default: bool
    description: str
    approximation_level: str


METRIC_CATALOG: tuple[MetricDefinition, ...] = (
    MetricDefinition("hr.resting_sleep_bpm", "Resting sleep HR", "heart", "bpm", False, None, "derived SQL", 7, True, True, "Lowest available daily heart-rate proxy; sleep-window when available.", "heuristic"),
    MetricDefinition("hr.daily_avg_bpm", "Daily average HR", "heart", "bpm", None, None, "H59 historical", 3, True, True, "Average historical heart-rate readings for the day.", "observed"),
    MetricDefinition("hrv.daily_median", "Daily HRV-like value", "recovery", "ms", True, None, "H59 historical", 14, True, True, "Vendor HRV-like value; useful for personal trends only.", "vendor-derived"),
    MetricDefinition("sleep.total_minutes", "Sleep duration", "sleep", "minutes", True, None, "H59 historical", 7, True, True, "Canonical overnight sleep-session duration.", "observed"),
    MetricDefinition("sleep.effective_minutes", "Effective sleep", "sleep", "minutes", True, None, "derived SQL", 7, True, False, "Sleep duration excluding no-data intervals when present.", "observed"),
    MetricDefinition("sleep.efficiency_pct", "Sleep efficiency", "sleep", "percent", True, None, "derived SQL", 7, True, True, "Effective minutes divided by total sleep-session minutes.", "heuristic"),
    MetricDefinition("sleep.restorative_minutes", "Restorative sleep", "sleep", "minutes", True, None, "derived SQL", 7, True, True, "Deep plus REM minutes from approximate wearable stages.", "heuristic"),
    MetricDefinition("sleep.stage_deep_pct", "Deep sleep %", "sleep", "percent", True, None, "derived SQL", 7, True, False, "Deep-stage percentage from wearable sleep staging.", "heuristic"),
    MetricDefinition("sleep.stage_rem_pct", "REM sleep %", "sleep", "percent", True, None, "derived SQL", 7, True, False, "REM-stage percentage from wearable sleep staging.", "heuristic"),
    MetricDefinition("activity.steps_total", "Steps", "activity", "steps", True, None, "H59 historical", 3, True, True, "Daily total steps from activity bins.", "observed"),
    MetricDefinition("activity.distance_total", "Distance", "activity", "m", True, None, "H59 historical", 3, True, False, "Daily distance from activity bins.", "observed"),
    MetricDefinition("activity.calories_total", "Calories", "activity", "kcal", True, None, "H59 historical", 3, True, False, "Vendor calorie estimate from activity bins.", "vendor-derived"),
    MetricDefinition("strain.activity_load", "Activity load", "strain", "load", False, None, "derived SQL", 7, True, True, "Simple steps/calories load proxy used when HR sampling is sparse.", "heuristic"),
    MetricDefinition("strain.score_0_21", "Daily strain", "strain", "score", False, None, "derived Python", 7, True, True, "Approximate 0-21 strain from activity load and HR elevation.", "experimental"),
    MetricDefinition("stress.pressure_avg", "Pressure/stress-like score", "stress", "score", False, None, "H59 historical", 7, True, True, "Vendor pressure/stress-like score; not a diagnosis.", "vendor-derived"),
    MetricDefinition("spo2.avg", "Average SpO2", "oxygen", "percent", True, None, "H59 historical", 3, True, True, "Average of captured SpO2 intervals.", "observed"),
    MetricDefinition("spo2.min", "Minimum SpO2", "oxygen", "percent", True, None, "H59 historical", 3, True, False, "Minimum captured SpO2 interval value.", "observed"),
    MetricDefinition("bp.latest_systolic", "Latest systolic BP", "blood_pressure", "mmHg", None, "Confirm outliers with repeated trusted measurements.", "H59 realtime health-check", 1, False, True, "Latest finished health-check systolic reading only; cuff-pressure streams are excluded.", "observed"),
    MetricDefinition("bp.latest_diastolic", "Latest diastolic BP", "blood_pressure", "mmHg", None, "Confirm outliers with repeated trusted measurements.", "H59 realtime health-check", 1, False, True, "Latest finished health-check diastolic reading only; cuff-pressure streams are excluded.", "observed"),
)

CATALOG_BY_KEY = {metric.metric_key: metric for metric in METRIC_CATALOG}


def robust_z_score(value: float | None, median: float | None, spread: float | None, *, higher_is_better: bool | None, clamp: float = 3.0) -> float | None:
    if value is None or median is None or spread is None or spread <= 0:
        return None
    z = (value - median) / (1.4826 * spread)
    if higher_is_better is False:
        z = -z
    return max(-clamp, min(clamp, z))


def _rows(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def metric_catalog_payload(*, category: str | None = None, dashboard_default: bool | None = None, baseline_supported: bool | None = None) -> dict[str, Any]:
    metrics = []
    for metric in METRIC_CATALOG:
        if category and metric.category != category:
            continue
        if dashboard_default is not None and metric.dashboard_default is not dashboard_default:
            continue
        if baseline_supported is not None and metric.baseline_supported is not baseline_supported:
            continue
        metrics.append(asdict(metric))
    return {"metrics": metrics, "count": len(metrics)}


def feature_series_payload(conn: sqlite3.Connection, metric_keys: list[str], *, device_id: int | None = None, from_value: str | None = None, to_value: str | None = None, include_baseline: bool = False) -> dict[str, Any]:
    series = []
    for key in metric_keys:
        if key not in CATALOG_BY_KEY:
            raise KeyError(key)
        clauses = ["feature_name=?"]
        params: list[Any] = [key]
        if device_id is not None:
            clauses.append("device_id=?")
            params.append(device_id)
        if from_value:
            clauses.append("feature_date>=date(?)")
            params.append(from_value)
        if to_value:
            clauses.append("feature_date<=date(?)")
            params.append(to_value)
        observations = _rows(
            conn,
            f"""
            SELECT device_id, feature_name AS metric_key, feature_date, valid_from, valid_to,
                   feature_value AS value, unit, source_kind, source_table, source_id,
                   data_quality_state, confidence, observation_as_of, approximation_label
            FROM health_feature_observations
            WHERE {' AND '.join(clauses)}
            ORDER BY feature_date, valid_from
            """,
            tuple(params),
        )
        if include_baseline and observations:
            baseline_rows = {
                (row["as_of_date"], row["window_days"]): row
                for row in _rows(
                    conn,
                    """
                    SELECT * FROM health_feature_baselines
                    WHERE feature_name=? AND window_days=30
                    ORDER BY as_of_date
                    """,
                    (key,),
                )
            }
            for obs in observations:
                baseline = baseline_rows.get((obs["feature_date"], 30))
                if baseline:
                    obs["baseline"] = baseline
        series.append({"metric": asdict(CATALOG_BY_KEY[key]), "metric_key": key, "observations": observations})
    return {"series": series}


def daily_feature_payload(conn: sqlite3.Connection, *, date_value: str | None = None, device_id: int | None = None) -> dict[str, Any]:
    clauses: list[str] = []
    params: list[Any] = []
    if date_value:
        clauses.append("day_value=date(?)")
        params.append(date_value)
    if device_id is not None:
        clauses.append("device_id=?")
        params.append(device_id)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    row = conn.execute(f"SELECT * FROM health_daily_feature_store {where} ORDER BY day_value DESC LIMIT 1", tuple(params)).fetchone()
    if row is None:
        return {"feature_date": date_value, "features": {}, "data_quality_state": "missing", "observation_as_of": None}
    data = dict(row)
    mapping = {
        "hr.resting_sleep_bpm": "resting_hr_bpm",
        "hr.daily_avg_bpm": "avg_hr",
        "hrv.daily_median": "hrv_avg",
        "sleep.total_minutes": "sleep_total_minutes",
        "sleep.efficiency_pct": "sleep_efficiency_pct",
        "sleep.restorative_minutes": "sleep_restorative_minutes",
        "activity.steps_total": "steps_total",
        "strain.score_0_21": "strain_score_0_21",
        "stress.pressure_avg": "pressure_avg",
        "spo2.avg": "spo2_avg",
        "spo2.min": "spo2_min",
        "bp.latest_systolic": "systolic_bp_latest",
        "bp.latest_diastolic": "diastolic_bp_latest",
    }
    features = {}
    for key, column in mapping.items():
        if column in data and data[column] is not None:
            metric = CATALOG_BY_KEY[key]
            features[key] = {"value": data[column], "unit": metric.unit, "approximation_level": metric.approximation_level}
    return {"device_id": data["device_id"], "feature_date": data["day_value"], "observation_as_of": data["observation_as_of"], "data_quality_state": data["data_quality_state"], "features": features}


def sleep_summary_payload(conn: sqlite3.Connection, *, date_value: str | None = None, from_value: str | None = None, to_value: str | None = None, include_stages: bool = False, device_id: int | None = None) -> dict[str, Any]:
    clauses = ["1=1"]
    params: list[Any] = []
    if date_value:
        clauses.append("sleep_day=date(?)")
        params.append(date_value)
    if from_value:
        clauses.append("sleep_day>=date(?)")
        params.append(from_value)
    if to_value:
        clauses.append("sleep_day<=date(?)")
        params.append(to_value)
    if device_id is not None:
        clauses.append("device_id=?")
        params.append(device_id)
    sessions = _rows(conn, f"SELECT * FROM analytic_sleep_sessions_canonical WHERE {' AND '.join(clauses)} ORDER BY sleep_day DESC", tuple(params))
    out = []
    for sess in sessions:
        stages = _rows(conn, "SELECT stage, valid_from, valid_to, minutes FROM analytic_sleep_stage_intervals WHERE sleep_session_id=? ORDER BY valid_from", (sess["sleep_session_id"],))
        by_stage: dict[str, float] = {}
        for stage in stages:
            by_stage[stage["stage"]] = by_stage.get(stage["stage"], 0) + float(stage["minutes"] or 0)
        total = float(sess.get("total_minutes") or 0)
        derived = {
            "efficiency_pct": round(100 * float(sess.get("effective_minutes") or 0) / total, 1) if total else None,
            "stage_minutes": by_stage,
            "stage_percentages": {k: round(100 * v / total, 1) for k, v in by_stage.items()} if total else {},
            "restorative_minutes": by_stage.get("deep", 0) + by_stage.get("rem", 0),
            "waso_minutes": by_stage.get("awake", 0) + by_stage.get("wake", 0),
            "disturbance_count": sum(1 for s in stages if s["stage"] in {"awake", "wake"}),
            "quality_flags": ["sleep_stages_approximate"] + (["provisional_session"] if sess.get("is_provisional") else []),
        }
        item = {"session": sess, "derived": derived}
        if include_stages:
            item["stages"] = stages
        out.append(item)
    return {"sessions": out, "safety_label": "Sleep stages are approximate wearable wellness analytics, not PSG-validated measurements."}


def strain_daily_payload(conn: sqlite3.Connection, *, device_id: int | None = None) -> dict[str, Any]:
    where = "WHERE device_id=?" if device_id is not None else ""
    params = (device_id,) if device_id is not None else ()
    rows = _rows(conn, f"SELECT device_id, day_value, steps_total, activity_load, resting_hr_bpm, avg_hr, max_hr, strain_score_0_21, data_quality_state FROM health_daily_feature_store {where} ORDER BY day_value", params)
    days = []
    for row in rows:
        confidence = 0.65 if row.get("avg_hr") is not None and row.get("steps_total") is not None else 0.35
        days.append({**row, "confidence": confidence, "approximation_label": "heuristic", "note": "Approximate strain; sparse HR/activity sampling lowers confidence."})
    return {"days": days}


def workouts_payload(conn: sqlite3.Connection, *, device_id: int | None = None) -> dict[str, Any]:
    days = strain_daily_payload(conn, device_id=device_id)["days"]
    bouts = []
    for day in days:
        if (day.get("steps_total") or 0) >= 5000 or (day.get("strain_score_0_21") or 0) >= 5:
            bouts.append({"date": day["day_value"], "start": day["day_value"] + "T00:00:00+00:00", "end": day["day_value"] + "T23:59:59+00:00", "duration_minutes": 60 if (day.get("steps_total") or 0) < 9000 else 120, "steps": day.get("steps_total"), "strain_contribution": day.get("strain_score_0_21"), "confidence": 0.45, "approximation_label": "coarse_daily_activity_bout", "evidence_sources": ["sport_details", "heart_rates"]})
    return {"bouts": bouts, "note": "Workout detection is coarse when activity bins are sparse or hourly."}


def _feature_points(conn: sqlite3.Connection, metric_key: str) -> list[dict[str, Any]]:
    return _rows(conn, "SELECT feature_date, feature_value AS value FROM health_feature_observations WHERE feature_name=? ORDER BY feature_date", (metric_key,))


def trends_payload(conn: sqlite3.Connection, metric_keys: list[str], *, window: int = 7) -> dict[str, Any]:
    series = []
    for key in metric_keys:
        pts = _feature_points(conn, key)
        enriched = []
        values: list[float] = []
        for point in pts:
            value = float(point["value"])
            values.append(value)
            recent = values[-window:]
            enriched.append({**point, "rolling_avg": round(mean(recent), 3), "delta_vs_prior": round(value - values[-window - 1], 3) if len(values) > window else None, "percentile_rank": round(100 * sum(v <= value for v in values) / len(values), 1)})
        series.append({"metric_key": key, "points": enriched})
    return {"series": series, "window": window}


def compare_payload(conn: sqlite3.Connection, metric_keys: list[str]) -> dict[str, Any]:
    maps = {key: {p["feature_date"]: p["value"] for p in _feature_points(conn, key)} for key in metric_keys}
    dates = sorted(set.intersection(*(set(m.keys()) for m in maps.values()))) if maps else []
    return {"metrics": metric_keys, "aligned_points": [{"feature_date": d, "values": {key: maps[key][d] for key in metric_keys}} for d in dates]}


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    mx, my = mean(xs), mean(ys)
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def correlation_payload(conn: sqlite3.Connection, x_metric_key: str, y_metric_key: str, *, lag_days: int = 0, max_lag_days: int | None = None, min_samples: int = 10) -> dict[str, Any]:
    def calc(lag: int) -> dict[str, Any]:
        x = {p["feature_date"]: float(p["value"]) for p in _feature_points(conn, x_metric_key)}
        y = {p["feature_date"]: float(p["value"]) for p in _feature_points(conn, y_metric_key)}
        import datetime as dt
        pairs = []
        for d, xv in x.items():
            yd = (dt.date.fromisoformat(d) + dt.timedelta(days=lag)).isoformat()
            if yd in y:
                pairs.append((xv, y[yd]))
        xs, ys = [p[0] for p in pairs], [p[1] for p in pairs]
        r = _pearson(xs, ys) if len(pairs) >= min_samples else None
        bucket = "insufficient" if len(pairs) < min_samples else ("high" if r is not None and abs(r) >= 0.7 else "medium" if r is not None and abs(r) >= 0.4 else "low")
        return {"lag_days": lag, "sample_count": len(pairs), "pearson_r": None if r is None else round(r, 4), "confidence_bucket": bucket}
    lag_table = [calc(lag) for lag in range(-max_lag_days, max_lag_days + 1)] if max_lag_days is not None else [calc(lag_days)]
    best = max(lag_table, key=lambda row: abs(row["pearson_r"] or 0))
    return {**best, "x_metric_key": x_metric_key, "y_metric_key": y_metric_key, "lag_table": lag_table, "interpretation": f"Exploratory local relationship between {x_metric_key} and {y_metric_key}; confidence is {best['confidence_bucket']} with {best['sample_count']} shared dates."}


def behavior_effect_payload(conn: sqlite3.Connection, event_key: str, target_metric_key: str, *, lag_days: int = 0, min_group: int = 3) -> dict[str, Any]:
    daily = _rows(conn, "SELECT * FROM health_daily_feature_store ORDER BY day_value")
    target = {p["feature_date"]: float(p["value"]) for p in _feature_points(conn, target_metric_key)}
    import datetime as dt
    values_with: list[float] = []
    values_without: list[float] = []
    steps = [float(r["steps_total"] or 0) for r in daily]
    step_threshold = sorted(steps)[int(len(steps) * 0.7)] if steps else 0
    for row in daily:
        is_event = False
        if event_key == "high-step-day":
            is_event = (row.get("steps_total") or 0) >= step_threshold
        elif event_key == "low-sleep-night":
            is_event = (row.get("sleep_total_minutes") or 0) < 360
        elif event_key == "high-pressure-day":
            is_event = (row.get("pressure_avg") or 0) >= 40
        elif event_key == "bp-measurement-day":
            is_event = row.get("systolic_bp_latest") is not None
        target_date = (dt.date.fromisoformat(row["day_value"]) + dt.timedelta(days=lag_days)).isoformat()
        if target_date in target:
            (values_with if is_event else values_without).append(target[target_date])
    mw = mean(values_with) if values_with else None
    mn = mean(values_without) if values_without else None
    delta = (mw - mn) if mw is not None and mn is not None else None
    confidence = "insufficient" if len(values_with) < min_group or len(values_without) < min_group else "exploratory"
    return {"event_key": event_key, "target_metric_key": target_metric_key, "lag_days": lag_days, "with_event_count": len(values_with), "without_event_count": len(values_without), "mean_with_event": mw, "mean_without_event": mn, "delta": delta, "confidence": confidence, "explanation": f"On {event_key} days, {target_metric_key} changed by {delta:.1f} on average." if delta is not None else "Not enough matched local data for a comparison."}
