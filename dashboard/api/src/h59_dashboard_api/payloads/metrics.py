from __future__ import annotations

import sqlite3
from typing import Any

from ..schemas import MetricPoint, MetricSeriesResponse
from ..time import range_start
from .common import quantile, summary


def metric_series_payload(conn: sqlite3.Connection, device_id: int, metric: str, range_name: str) -> MetricSeriesResponse:
    start_iso = range_start(range_name).isoformat()

    if metric == "heart-rate" and range_name == "7d":
        rows = conn.execute(
            """
            SELECT date(valid_from) AS day_value, value
            FROM analytic_heart_rate_intervals
            WHERE device_id=? AND valid_from>=?
            ORDER BY valid_from ASC
            """,
            (device_id, start_iso),
        ).fetchall()
        buckets: dict[str, list[int]] = {}
        for row in rows:
            buckets.setdefault(str(row["day_value"]), []).append(int(row["value"]))
        points = [
            MetricPoint(
                timestamp=f"{day_value}T00:00:00+00:00",
                value=quantile(values, 0.5),
                min_value=min(values),
                max_value=max(values),
                lower_quartile=quantile(values, 0.25),
                median_value=quantile(values, 0.5),
                upper_quartile=quantile(values, 0.75),
            )
            for day_value, values in sorted(buckets.items())
            if values
        ]
        flat_values = [value for values in buckets.values() for value in values]
        return MetricSeriesResponse(
            metric=metric,
            label="Heart Rate",
            unit="bpm",
            trust_class="measured",
            range=range_name,
            available=bool(points),
            points=points,
            latest_value=points[-1].median_value if points else None,
            summary=summary([float(v) for v in flat_values]) if flat_values else None,
        )

    if metric == "blood-pressure":
        return MetricSeriesResponse(
            metric=metric,
            label="Blood Pressure Estimate",
            unit="mmHg",
            trust_class="estimated",
            range=range_name,
            available=False,
            note="Historical blood-pressure extraction is not currently proven for this device.",
        )

    configs: dict[str, dict[str, Any]] = {
        "heart-rate": {
            "table": "analytic_heart_rate_intervals",
            "label": "Heart Rate",
            "unit": "bpm",
            "trust": "measured",
            "point_builder": lambda row: MetricPoint(timestamp=row["valid_from"], value=int(row["value"])),
        },
        "hrv": {
            "table": "analytic_hrv_intervals",
            "label": "HRV",
            "unit": "ms",
            "trust": "derived",
            "point_builder": lambda row: MetricPoint(timestamp=row["valid_from"], value=int(row["value"])),
        },
        "stress": {
            "table": "analytic_pressure_intervals",
            "label": "Stress",
            "unit": None,
            "trust": "vendor_score",
            "point_builder": lambda row: MetricPoint(timestamp=row["valid_from"], value=int(row["value"])),
        },
        "spo2": {
            "table": "analytic_blood_oxygen_intervals",
            "label": "Blood Oxygen",
            "unit": "%",
            "trust": "derived",
            "point_builder": lambda row: MetricPoint(
                timestamp=row["valid_from"],
                value=float(row["value"]),
                min_value=int(row["min_percent"]),
                max_value=int(row["max_percent"]),
            ),
        },
        "steps": {
            "table": "analytic_daily_steps",
            "label": "Steps",
            "unit": "steps",
            "trust": "derived",
            "point_builder": lambda row: MetricPoint(timestamp=row["valid_from"], value=int(row["steps_total"])),
        },
    }
    if metric not in configs:
        raise KeyError(metric)

    config = configs[metric]
    rows = conn.execute(
        f"""
        SELECT *
        FROM {config['table']}
        WHERE device_id=? AND valid_from>=?
        ORDER BY valid_from ASC
        """,
        (device_id, start_iso),
    ).fetchall()
    points = [config["point_builder"](row) for row in rows]
    values = [point.value for point in points if point.value is not None]
    return MetricSeriesResponse(
        metric=metric,
        label=config["label"],
        unit=config["unit"],
        trust_class=config["trust"],
        range=range_name,
        available=bool(points),
        points=points,
        latest_value=values[-1] if values else None,
        summary=summary([float(v) for v in values]) if values else None,
    )
