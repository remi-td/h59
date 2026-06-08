from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


TrustClass = Literal["measured", "derived", "estimated", "vendor_score", "unknown"]
FreshnessClass = Literal["fresh", "partial", "stale", "empty", "error"]
TrendType = Literal["line", "boxplot", "none"]


class TimeContext(BaseModel):
    storage_timezone: Literal["UTC"] = "UTC"
    display_timezone: Literal["browser-local"] = "browser-local"
    query_day_boundary_timezone: Literal["UTC"] = "UTC"
    interval_model: Literal["[from, to["] = "[from, to["


class DeviceSummary(BaseModel):
    id: int
    nickname: str | None = None
    name: str | None = None
    address: str
    battery_percent: int | None = None
    last_sync: str | None = None
    data_freshness: FreshnessClass
    is_preferred: bool = False


class SyncContext(BaseModel):
    latest_band_sync: str | None = None
    sync_age_minutes: int | None = None
    data_freshness: FreshnessClass
    is_stale: bool
    data_as_of: str | None = None
    data_age_minutes: int | None = None
    warning: str | None = None


class MetricSummary(BaseModel):
    min: float | None = None
    max: float | None = None
    avg: float | None = None


class MetricPoint(BaseModel):
    timestamp: str
    value: float | int | None = None
    min_value: float | int | None = None
    max_value: float | int | None = None
    lower_quartile: float | int | None = None
    median_value: float | int | None = None
    upper_quartile: float | int | None = None
    label: str | None = None


class MetricBreakdownItem(BaseModel):
    label: str
    value: float | int


class MetricCard(BaseModel):
    id: str
    title: str
    value: float | int | str | None = None
    unit: str | None = None
    display_value: str | None = None
    trust_class: TrustClass
    status: FreshnessClass = "fresh"
    summary: MetricSummary | None = None
    subtitle: str | None = None
    trend: str | None = None
    trend_type: TrendType = "line"
    sparkline: list[MetricPoint] = Field(default_factory=list)
    breakdown: list[MetricBreakdownItem] = Field(default_factory=list)


class TodayResponse(BaseModel):
    date: str
    time_context: TimeContext
    device: DeviceSummary
    cards: list[MetricCard]


class HealthResponse(BaseModel):
    status: Literal["ok", "missing_database", "empty_database"]
    db_path: str
    device_count: int
    time_context: TimeContext


class MetricSeriesResponse(BaseModel):
    metric: str
    label: str
    unit: str | None = None
    trust_class: TrustClass
    range: str
    available: bool
    points: list[MetricPoint] = Field(default_factory=list)
    latest_value: float | int | None = None
    summary: MetricSummary | None = None
    note: str | None = None
    time_context: TimeContext


class SleepStageSegment(BaseModel):
    stage: str
    start_timestamp: str | None = None
    end_timestamp: str | None = None
    minutes: int
    is_provisional: bool


class SleepSessionSummary(BaseModel):
    start_timestamp: str | None = None
    end_timestamp: str | None = None
    total_minutes: int | None = None
    state: str | None = None
    score: float | None = None
    is_provisional: bool
    stages: list[SleepStageSegment] = Field(default_factory=list)


class SleepResponse(BaseModel):
    range: str
    available: bool
    sessions: list[SleepSessionSummary] = Field(default_factory=list)
    latest_session: SleepSessionSummary | None = None
    daily_totals: list[MetricPoint] = Field(default_factory=list)
    time_context: TimeContext


class DeviceStatusResponse(BaseModel):
    device: DeviceSummary
    battery_charging: bool | None = None
    last_sample_timestamp: str | None = None
    latest_samples: dict[str, str | None]
    time_context: TimeContext


class DataQualityResponse(BaseModel):
    device_id: int
    status: FreshnessClass
    last_successful_sync: str | None = None
    sample_counts_today: dict[str, int]
    latest_sample_timestamps: dict[str, str | None]
    sleep_record_present: bool
    missing_metrics: list[str]
    time_context: TimeContext


class DebugResponse(BaseModel):
    device: DeviceSummary
    table_counts: dict[str, int]
    recent_syncs: list[dict[str, str | int | None]]
    time_context: TimeContext


class InsightScore(BaseModel):
    score: float
    band: str


class InsightSleep(BaseModel):
    score: float
    duration_minutes: int | None = None
    debt_minutes_7d: int | None = None


class CurrentInsightResponse(BaseModel):
    as_of: str | None = None
    device: DeviceSummary | None = None
    sync_context: SyncContext
    confidence: Literal["low", "medium", "high"]
    state: str
    readiness: InsightScore
    sleep: InsightSleep
    strain: InsightScore
    key_factors: list[str]
    safety_flags: list[str]
    recommended_action: str
    llm_guardrails: list[str]
