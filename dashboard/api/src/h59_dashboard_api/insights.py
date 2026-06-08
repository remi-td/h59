from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from .feature_store import CATALOG_BY_KEY, robust_z_score

Confidence = Literal["low", "medium", "high"]
State = Literal[
    "stable",
    "under_recovered",
    "sleep_deprived",
    "physiological_strain",
    "high_strain",
    "measurement_uncertain",
]


@dataclass(frozen=True)
class ScoreBand:
    score: float
    band: str


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _baseline(conn: sqlite3.Connection, device_id: int, day_value: str, metric: str, window_days: int = 30) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM health_metric_baselines
        WHERE device_id=? AND as_of_day=? AND metric=? AND window_days=?
        """,
        (device_id, day_value, metric, window_days),
    ).fetchone()


def _latest_feature(conn: sqlite3.Connection, device_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM health_daily_features
        WHERE device_id=?
        ORDER BY day_value DESC
        LIMIT 1
        """,
        (device_id,),
    ).fetchone()


def _num(row: sqlite3.Row | None, key: str) -> float | None:
    if row is None:
        return None
    value = row[key]
    if value is None:
        return None
    return float(value)


def _readiness_band(score: float) -> str:
    if score >= 85:
        return "strong"
    if score >= 70:
        return "normal"
    if score >= 50:
        return "mixed"
    if score >= 30:
        return "strained"
    return "unusually_strained"


def _strain_band(score: float) -> str:
    if score < 10:
        return "light"
    if score < 14:
        return "moderate"
    if score < 18:
        return "high"
    return "very_high"


def _baseline_delta(value: float | None, baseline: sqlite3.Row | None) -> tuple[float | None, float | None]:
    median = _num(baseline, "median")
    if value is None or median is None:
        return None, median
    return value - median, median


def _confidence(feature: sqlite3.Row, baselines: list[sqlite3.Row | None]) -> Confidence:
    quality = _num(feature, "data_quality_score") or 0.0
    max_days = max((int(row["n_days"]) for row in baselines if row is not None), default=0)
    if quality >= 60 and max_days >= 30:
        return "high"
    if quality >= 35 and max_days >= 7:
        return "medium"
    return "low"


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _sync_context(device_summary: Any, *, data_as_of: str | None) -> dict[str, Any]:
    last_sync = device_summary.last_sync
    last_sync_dt = _parse_timestamp(last_sync)
    data_as_of_dt = _parse_timestamp(data_as_of)
    now = datetime.now(UTC)
    age_minutes = None
    if last_sync_dt is not None:
        age_minutes = max(0, int((now - last_sync_dt).total_seconds() // 60))
    data_age_minutes = None
    if data_as_of_dt is not None:
        data_age_minutes = max(0, int((now - data_as_of_dt).total_seconds() // 60))
    freshness = device_summary.freshness
    is_stale = freshness in {"stale", "empty", "error"} or (data_age_minutes is not None and data_age_minutes > 360)
    warning = None
    if freshness == "empty":
        warning = "No completed band sync is available; health inference is not current."
    elif freshness == "error":
        warning = "Band sync status is uncertain; health inference may be incomplete."
    elif freshness == "stale":
        warning = "Band data is stale; health inference may describe an earlier physical state, not the current one."
    elif freshness == "partial":
        warning = "Band data is not fresh; interpret current-state advice with caution."
    if data_age_minutes is None and data_as_of is None:
        warning = warning or "No dated health feature row is available yet."
    elif data_age_minutes is not None and data_age_minutes > 360:
        warning = "Latest health features are stale; current-state advice may describe an earlier physical state."
    elif data_age_minutes is not None and data_age_minutes > 60:
        warning = warning or "Latest health features are not recent; interpret current-state advice with caution."
    return {
        "latest_band_sync": last_sync,
        "sync_age_minutes": age_minutes,
        "data_freshness": freshness,
        "is_stale": is_stale,
        "data_as_of": data_as_of,
        "data_age_minutes": data_age_minutes,
        "warning": warning,
    }


def _downgrade_confidence_for_context(confidence: Confidence, sync_context: dict[str, Any]) -> Confidence:
    freshness = sync_context["data_freshness"]
    data_age_minutes = sync_context.get("data_age_minutes")
    if freshness in {"stale", "empty", "error"}:
        return "low"
    if freshness == "partial" and confidence == "high":
        return "medium"
    if data_age_minutes is None:
        return "low"
    if data_age_minutes > 360:
        return "low"
    if data_age_minutes > 60 and confidence == "high":
        return "medium"
    return confidence


def current_insight_payload(conn: sqlite3.Connection, device_summary: Any, *, is_preferred: bool = False) -> dict[str, Any]:
    """Compute deterministic, explainable health insight scores from DB feature views.

    This module deliberately keeps predictive/scoring logic in Python while the
    reusable feature and baseline definitions remain in SQLite views.
    """
    device_id = int(device_summary.row["device_id"] if hasattr(device_summary, "row") else device_summary["device_id"])
    feature = _latest_feature(conn, device_id)
    if feature is None:
        sync_context = _sync_context(device_summary, data_as_of=None)
        return {
            "as_of": None,
            "device": None,
            "sync_context": sync_context,
            "confidence": "low",
            "state": "measurement_uncertain",
            "readiness": {"score": 0, "band": "unavailable"},
            "sleep": {"score": 0, "duration_minutes": None, "debt_minutes_7d": None},
            "strain": {"score": 0, "band": "unavailable"},
            "key_factors": ["No reusable health feature rows are available yet."],
            "safety_flags": [],
            "recommended_action": "Keep collecting data before drawing conclusions.",
            "llm_guardrails": ["Do not diagnose from missing wearable data."],
            "feature_context": {"observation_as_of": None, "feature_date": None, "data_quality_score": None},
        }

    day = str(feature["day_value"])
    hrv_base = _baseline(conn, device_id, day, "hrv_avg")
    rhr_base = _baseline(conn, device_id, day, "resting_hr_bpm")
    sleep_base = _baseline(conn, device_id, day, "sleep_total_minutes")
    load_base = _baseline(conn, device_id, day, "activity_load")
    baselines = [hrv_base, rhr_base, sleep_base, load_base]

    hrv = _num(feature, "hrv_avg")
    rhr = _num(feature, "resting_hr_bpm")
    sleep_minutes = _num(feature, "sleep_total_minutes")
    activity_load = _num(feature, "activity_load") or 0.0
    spo2_min = _num(feature, "spo2_min")
    systolic = _num(feature, "systolic_bp_latest")
    diastolic = _num(feature, "diastolic_bp_latest")

    hrv_delta, hrv_median = _baseline_delta(hrv, hrv_base)
    rhr_delta, rhr_median = _baseline_delta(rhr, rhr_base)
    load_delta, load_median = _baseline_delta(activity_load, load_base)

    sleep_target = 450.0
    sleep_score = 50.0
    if sleep_minutes is not None:
        sleep_score = _clamp(100.0 - abs(sleep_target - sleep_minutes) / sleep_target * 100.0)
        if sleep_minutes < 360:
            sleep_score -= 15
        if sleep_minutes < 300:
            sleep_score -= 20
    sleep_score = round(_clamp(sleep_score), 1)

    hrv_component = 65.0
    if hrv is not None and hrv_median:
        hrv_component = _clamp(70.0 + ((hrv - hrv_median) / max(abs(hrv_median), 1.0)) * 80.0)

    rhr_component = 65.0
    if rhr is not None and rhr_median is not None:
        rhr_component = _clamp(80.0 - max(0.0, rhr - rhr_median) * 5.0 + max(0.0, rhr_median - rhr) * 1.0)

    load_penalty = 0.0
    if load_delta is not None and load_median is not None:
        load_penalty = max(0.0, load_delta / max(load_median, 1.0) * 10.0)

    safety_penalty = 0.0
    safety_flags: list[str] = []
    if spo2_min is not None and spo2_min < 92:
        safety_flags.append("Low wrist SpO2 trend; verify sensor fit and confirm with a trusted oximeter if repeated or symptomatic.")
        safety_penalty += 10
    if systolic is not None and diastolic is not None and (systolic >= 140 or diastolic >= 90):
        safety_flags.append("Elevated wearable BP observation; confirm with a validated upper-arm cuff before drawing conclusions.")
        safety_penalty += 8

    readiness = round(_clamp((0.35 * hrv_component) + (0.25 * rhr_component) + (0.30 * sleep_score) + 10.0 - load_penalty - safety_penalty), 1)

    strain_raw = activity_load
    strain_score = round(min(21.0, max(0.0, strain_raw * 1.4)), 1)

    key_factors: list[str] = []
    if hrv is not None and hrv_median:
        pct = ((hrv - hrv_median) / hrv_median) * 100.0
        key_factors.append(f"HRV {pct:+.0f}% vs 30-day median ({hrv:.0f} vs {hrv_median:.0f}).")
    if rhr is not None and rhr_median is not None:
        key_factors.append(f"resting HR {rhr_delta:+.0f} bpm vs 30-day median ({rhr:.0f} vs {rhr_median:.0f}).")
    if sleep_minutes is not None:
        key_factors.append(f"Sleep {int(sleep_minutes)} minutes vs {int(sleep_target)} minute target.")
    if load_delta is not None and load_median is not None:
        key_factors.append(f"Activity load {load_delta:+.1f} vs 30-day median.")
    if not key_factors:
        key_factors.append("Limited data; score confidence is low.")

    state: State = "stable"
    if sleep_minutes is not None and sleep_minutes < 360:
        state = "sleep_deprived"
    if (hrv_delta is not None and hrv_median and hrv_delta < -0.2 * hrv_median) and (rhr_delta is not None and rhr_delta >= 5):
        state = "physiological_strain"
    elif readiness < 70:
        state = "under_recovered"
    if strain_score >= 14 and readiness < 70 and state not in {"physiological_strain", "sleep_deprived"}:
        state = "high_strain"
    sync_context = _sync_context(device_summary, data_as_of=feature["observation_as_of"])
    confidence = _downgrade_confidence_for_context(_confidence(feature, baselines), sync_context)
    if sync_context["warning"]:
        key_factors.insert(0, sync_context["warning"])
    if confidence == "low":
        state = "measurement_uncertain"

    if state in {"physiological_strain", "under_recovered", "sleep_deprived", "high_strain"}:
        action = "Keep intensity light to moderate, prioritize hydration and sleep, and watch for symptoms or persistence."
    elif state == "measurement_uncertain":
        action = "Treat this as a low-confidence estimate until more baseline data is available."
    else:
        action = "Physiology looks broadly stable; keep normal routines unless symptoms or context suggest otherwise."

    components: list[dict[str, Any]] = []
    omitted_terms: list[str] = []
    component_specs = [
        ("hrv.daily_median", "HRV", hrv, hrv_base, 0.35, True),
        ("hr.resting_sleep_bpm", "Resting HR", rhr, rhr_base, 0.25, False),
        ("sleep.total_minutes", "Sleep duration", sleep_minutes, sleep_base, 0.30, True),
        ("strain.activity_load", "Activity load", activity_load, load_base, -0.10, False),
    ]
    for metric_key, label, value, baseline, weight, higher_is_better in component_specs:
        median = _num(baseline, "median")
        spread = None
        if baseline is not None and baseline["max"] is not None and baseline["min"] is not None:
            spread = max((float(baseline["max"]) - float(baseline["min"])) / 4.0, 1.0)
        rz = robust_z_score(value, median, spread, higher_is_better=higher_is_better)
        if value is None:
            omitted_terms.append(f"{label} missing or unsupported for the latest feature day.")
            continue
        contribution = (rz or 0.0) * abs(weight) * 10.0
        direction = "positive" if contribution >= 0 else "negative"
        metric = CATALOG_BY_KEY.get(metric_key)
        components.append(
            {
                "metric_key": metric_key,
                "label": metric.label if metric else label,
                "value": value,
                "baseline": median,
                "delta": None if median is None else value - median,
                "robust_z": rz,
                "weight": abs(weight),
                "contribution": round(contribution, 3),
                "direction": direction,
                "confidence": 0.7 if baseline is not None else 0.45,
            }
        )
    drivers_positive = sorted((c for c in components if c["contribution"] >= 0), key=lambda c: c["contribution"], reverse=True)[:3]
    drivers_negative = sorted((c for c in components if c["contribution"] < 0), key=lambda c: c["contribution"])[:3]

    return {
        "as_of": feature["observation_as_of"],
        "device": {
            "id": int(device_summary.row["device_id"]),
            "nickname": device_summary.row["nickname"],
            "name": device_summary.row["name"],
            "address": device_summary.row["address"],
            "battery_percent": device_summary.battery_percent,
            "last_sync": device_summary.last_sync,
            "data_freshness": device_summary.freshness,
            "is_preferred": is_preferred,
        },
        "sync_context": sync_context,
        "confidence": confidence,
        "state": state,
        "readiness": {
            "score": readiness,
            "score_0_100": readiness,
            "band": _readiness_band(readiness),
            "label": "measurement_uncertain" if confidence == "low" else ("primed" if readiness >= 85 else "balanced" if readiness >= 70 else "strained" if readiness >= 50 else "run_down"),
            "components": components,
            "drivers_positive": drivers_positive,
            "drivers_negative": drivers_negative,
            "omitted_terms": omitted_terms,
        },
        "sleep": {"score": sleep_score, "duration_minutes": int(sleep_minutes) if sleep_minutes is not None else None, "debt_minutes_7d": None},
        "strain": {"score": strain_score, "band": _strain_band(strain_score)},
        "key_factors": key_factors,
        "safety_flags": safety_flags,
        "recommended_action": action,
        "llm_guardrails": [
            "Do not diagnose illness, hypertension, hypoxia, or overtraining from this wearable pattern.",
            "Cite computed contributors and confidence when giving advice.",
            "Treat wearable BP and SpO2 as trend/safety signals requiring confirmation when abnormal.",
            "Always check sync_context.latest_band_sync and sync_context.data_freshness before treating this as current physiology.",
        ],
        "feature_context": {
            "observation_as_of": feature["observation_as_of"],
            "feature_date": day,
            "data_quality_score": feature["data_quality_score"],
        },
    }
