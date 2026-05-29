from __future__ import annotations

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings, get_settings
from .db import connect
from .device_context import preferred_device_id, require_device_context
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
            return HealthResponse(status="missing_database", db_path=str(settings.db_path), device_count=0)

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
