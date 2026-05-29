"""Compatibility export surface for dashboard payload builders.

The payload implementation now lives in domain modules under `payloads/`.
"""

from .payloads import (
    ResolvedDevice,
    data_quality_payload,
    debug_payload,
    device_status_payload,
    device_summary_payload,
    devices_payload,
    ensure_analytic_surface,
    health_payload,
    latest_metric_day,
    metric_series_payload,
    resolve_device_summary,
    sleep_payload,
    today_payload,
)

__all__ = [
    "ResolvedDevice",
    "data_quality_payload",
    "debug_payload",
    "device_status_payload",
    "device_summary_payload",
    "devices_payload",
    "ensure_analytic_surface",
    "health_payload",
    "latest_metric_day",
    "metric_series_payload",
    "resolve_device_summary",
    "sleep_payload",
    "today_payload",
]
