from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


TrustClass = Literal["measured", "derived", "estimated", "vendor_score", "unknown"]
FreshnessClass = Literal["fresh", "partial", "stale", "empty", "error"]
TrendType = Literal["line", "boxplot", "none"]


class DeviceSummary(BaseModel):
    id: int
    nickname: str | None = None
    name: str | None = None
    address: str
    battery_percent: int | None = None
    last_sync: str | None = None
    data_freshness: FreshnessClass
    is_preferred: bool = False


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
    device: DeviceSummary
    cards: list[MetricCard]


class HealthResponse(BaseModel):
    status: Literal["ok", "missing_database", "empty_database"]
    db_path: str
    device_count: int


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


class DeviceStatusResponse(BaseModel):
    device: DeviceSummary
    battery_charging: bool | None = None
    last_sample_timestamp: str | None = None
    latest_samples: dict[str, str | None]


class DataQualityResponse(BaseModel):
    device_id: int
    status: FreshnessClass
    last_successful_sync: str | None = None
    sample_counts_today: dict[str, int]
    latest_sample_timestamps: dict[str, str | None]
    sleep_record_present: bool
    missing_metrics: list[str]


class DebugResponse(BaseModel):
    device: DeviceSummary
    table_counts: dict[str, int]
    recent_syncs: list[dict[str, str | int | None]]
