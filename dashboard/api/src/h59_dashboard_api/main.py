from __future__ import annotations

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings, get_settings
from .db import connect
from .device_context import preferred_device_id, require_device_context
from .feature_store import (
    behavior_effect_payload,
    compare_payload,
    correlation_payload,
    daily_feature_payload,
    feature_series_payload,
    metric_catalog_payload,
    sleep_summary_payload,
    strain_daily_payload,
    trends_payload,
    workouts_payload,
)
from .insights import current_insight_payload
from .queries import (
    data_quality_payload,
    debug_payload,
    device_status_payload,
    devices_payload,
    ensure_analytic_surface,
    health_payload,
    metric_series_payload,
    sleep_payload,
    today_payload,
)
from .schemas import (
    CurrentInsightResponse,
    DataQualityResponse,
    DebugResponse,
    DeviceStatusResponse,
    DeviceSummary,
    HealthResponse,
    MetricSeriesResponse,
    SleepResponse,
    TodayResponse,
)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="h59 dashboard api", version="0.0.1")
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health", response_model=HealthResponse)
    def api_health() -> HealthResponse:
        try:
            with connect(settings) as conn:
                ensure_analytic_surface(conn)
                return health_payload(conn, str(settings.db_path))
        except FileNotFoundError:
            from .schemas import TimeContext
            return HealthResponse(status="missing_database", db_path=str(settings.db_path), device_count=0, time_context=TimeContext())

    @app.get("/api/devices", response_model=list[DeviceSummary])
    def api_devices() -> list[DeviceSummary]:
        with connect(settings) as conn:
            ensure_analytic_surface(conn)
            return devices_payload(conn, preferred_device_id(conn))

    @app.get("/api/today", response_model=TodayResponse)
    def api_today(device: str = Query(default="preferred")) -> TodayResponse:
        with connect(settings) as conn:
            ensure_analytic_surface(conn)
            context = require_device_context(conn, device)
            return today_payload(conn, context.resolved, is_preferred=context.is_preferred)

    @app.get("/api/metrics/catalog")
    def api_metric_catalog(
        category: str | None = Query(default=None),
        dashboard_default: bool | None = Query(default=None),
        baseline_supported: bool | None = Query(default=None),
    ) -> dict:
        return metric_catalog_payload(category=category, dashboard_default=dashboard_default, baseline_supported=baseline_supported)

    @app.get("/api/metrics/{metric}", response_model=MetricSeriesResponse)
    def api_metric(metric: str, device: str = Query(default="preferred"), range: str = Query(default="30d")) -> MetricSeriesResponse:
        with connect(settings) as conn:
            ensure_analytic_surface(conn)
            context = require_device_context(conn, device)
            try:
                return metric_series_payload(conn, int(context.resolved.row["device_id"]), metric, range)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=f"unsupported metric: {metric}") from exc

    @app.get("/api/sleep", response_model=SleepResponse)
    def api_sleep(device: str = Query(default="preferred"), range: str = Query(default="30d")) -> SleepResponse:
        with connect(settings) as conn:
            ensure_analytic_surface(conn)
            context = require_device_context(conn, device)
            return sleep_payload(conn, int(context.resolved.row["device_id"]), range)

    @app.get("/api/device/status", response_model=DeviceStatusResponse)
    def api_device_status(device: str = Query(default="preferred")) -> DeviceStatusResponse:
        with connect(settings) as conn:
            ensure_analytic_surface(conn)
            context = require_device_context(conn, device)
            return device_status_payload(conn, context.resolved, is_preferred=context.is_preferred)

    @app.get("/api/data-quality", response_model=DataQualityResponse)
    def api_data_quality(device: str = Query(default="preferred")) -> DataQualityResponse:
        with connect(settings) as conn:
            ensure_analytic_surface(conn)
            context = require_device_context(conn, device)
            return data_quality_payload(conn, context.resolved)

    @app.get("/api/insights/current", response_model=CurrentInsightResponse)
    def api_current_insight(device: str = Query(default="preferred")) -> CurrentInsightResponse:
        with connect(settings) as conn:
            ensure_analytic_surface(conn)
            context = require_device_context(conn, device)
            return CurrentInsightResponse.model_validate(current_insight_payload(conn, context.resolved, is_preferred=context.is_preferred))

    @app.get("/api/features")
    def api_features(
        metric_key: list[str] = Query(),
        device: str | None = Query(default=None),
        from_: str | None = Query(default=None, alias="from"),
        to: str | None = Query(default=None),
        granularity: str = Query(default="daily"),
        include_baseline: bool = Query(default=False),
    ) -> dict:
        if granularity not in {"raw", "interval", "daily", "weekly"}:
            raise HTTPException(status_code=400, detail="unsupported granularity")
        with connect(settings) as conn:
            ensure_analytic_surface(conn)
            device_id = None
            if device:
                context = require_device_context(conn, device)
                device_id = int(context.resolved.row["device_id"])
            try:
                return feature_series_payload(conn, metric_key, device_id=device_id, from_value=from_, to_value=to, include_baseline=include_baseline)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=f"unsupported metric: {exc.args[0]}") from exc

    @app.get("/api/features/daily")
    def api_features_daily(date: str | None = Query(default=None), device: str | None = Query(default=None)) -> dict:
        with connect(settings) as conn:
            ensure_analytic_surface(conn)
            device_id = None
            if device:
                context = require_device_context(conn, device)
                device_id = int(context.resolved.row["device_id"])
            return daily_feature_payload(conn, date_value=date, device_id=device_id)

    @app.get("/api/sleep/summary")
    def api_sleep_summary(
        date: str | None = Query(default=None),
        from_: str | None = Query(default=None, alias="from"),
        to: str | None = Query(default=None),
        include_stages: bool = Query(default=False),
        device: str | None = Query(default=None),
    ) -> dict:
        with connect(settings) as conn:
            ensure_analytic_surface(conn)
            device_id = None
            if device:
                context = require_device_context(conn, device)
                device_id = int(context.resolved.row["device_id"])
            return sleep_summary_payload(conn, date_value=date, from_value=from_, to_value=to, include_stages=include_stages, device_id=device_id)

    @app.get("/api/strain/daily")
    def api_strain_daily(device: str | None = Query(default=None)) -> dict:
        with connect(settings) as conn:
            ensure_analytic_surface(conn)
            device_id = None
            if device:
                context = require_device_context(conn, device)
                device_id = int(context.resolved.row["device_id"])
            return strain_daily_payload(conn, device_id=device_id)

    @app.get("/api/workouts")
    def api_workouts(device: str | None = Query(default=None)) -> dict:
        with connect(settings) as conn:
            ensure_analytic_surface(conn)
            device_id = None
            if device:
                context = require_device_context(conn, device)
                device_id = int(context.resolved.row["device_id"])
            return workouts_payload(conn, device_id=device_id)

    @app.get("/api/trends")
    def api_trends(metric_key: list[str] = Query(), window: int = Query(default=7)) -> dict:
        with connect(settings) as conn:
            ensure_analytic_surface(conn)
            return trends_payload(conn, metric_key, window=window)

    @app.get("/api/compare")
    def api_compare(metric_key: list[str] = Query()) -> dict:
        with connect(settings) as conn:
            ensure_analytic_surface(conn)
            return compare_payload(conn, metric_key)

    @app.get("/api/correlations")
    def api_correlations(
        x_metric_key: str = Query(),
        y_metric_key: str = Query(),
        lag_days: int = Query(default=0),
        max_lag_days: int | None = Query(default=None),
    ) -> dict:
        with connect(settings) as conn:
            ensure_analytic_surface(conn)
            return correlation_payload(conn, x_metric_key, y_metric_key, lag_days=lag_days, max_lag_days=max_lag_days)

    @app.get("/api/behavior-effects")
    def api_behavior_effects(event_key: str = Query(), target_metric_key: str = Query(), lag_days: int = Query(default=0)) -> dict:
        with connect(settings) as conn:
            ensure_analytic_surface(conn)
            return behavior_effect_payload(conn, event_key, target_metric_key, lag_days=lag_days)

    @app.get("/api/debug", response_model=DebugResponse)
    def api_debug(device: str = Query(default="preferred")) -> DebugResponse:
        with connect(settings) as conn:
            ensure_analytic_surface(conn)
            context = require_device_context(conn, device)
            return debug_payload(conn, context.resolved, is_preferred=context.is_preferred)

    return app


app = create_app()


def run() -> None:
    settings = get_settings()
    uvicorn.run("h59_dashboard_api.main:app", host=settings.host, port=settings.port, reload=False)
