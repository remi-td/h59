export type FreshnessClass = "fresh" | "partial" | "stale" | "empty" | "error";
export type TrustClass = "measured" | "derived" | "estimated" | "vendor_score" | "unknown";
export type TrendType = "line" | "boxplot" | "none";

export interface DeviceSummary {
  id: number;
  nickname?: string | null;
  name?: string | null;
  address: string;
  battery_percent?: number | null;
  last_sync?: string | null;
  data_freshness: FreshnessClass;
  is_preferred: boolean;
}

export interface MetricSummary {
  min?: number | null;
  max?: number | null;
  avg?: number | null;
}

export interface MetricBreakdownItem {
  label: string;
  value: number;
}

export interface MetricCardData {
  id: string;
  title: string;
  value?: number | string | null;
  unit?: string | null;
  display_value?: string | null;
  trust_class: TrustClass;
  status: FreshnessClass;
  summary?: MetricSummary | null;
  subtitle?: string | null;
  trend?: string | null;
  trend_type: TrendType;
  sparkline: MetricPoint[];
  breakdown: MetricBreakdownItem[];
}

export interface TodayResponse {
  date: string;
  device: DeviceSummary;
  cards: MetricCardData[];
}

export interface MetricPoint {
  timestamp: string;
  value?: number | null;
  min_value?: number | null;
  max_value?: number | null;
  lower_quartile?: number | null;
  median_value?: number | null;
  upper_quartile?: number | null;
  label?: string | null;
}

export interface MetricSeriesResponse {
  metric: string;
  label: string;
  unit?: string | null;
  trust_class: TrustClass;
  range: string;
  available: boolean;
  points: MetricPoint[];
  latest_value?: number | null;
  summary?: MetricSummary | null;
  note?: string | null;
}

export interface SleepStageSegment {
  stage: string;
  start_timestamp?: string | null;
  end_timestamp?: string | null;
  minutes: number;
  is_provisional: boolean;
}

export interface SleepSessionSummary {
  start_timestamp?: string | null;
  end_timestamp?: string | null;
  total_minutes?: number | null;
  state?: string | null;
  score?: number | null;
  is_provisional: boolean;
  stages: SleepStageSegment[];
}

export interface SleepResponse {
  range: string;
  available: boolean;
  sessions: SleepSessionSummary[];
  latest_session?: SleepSessionSummary | null;
  daily_totals: MetricPoint[];
}

export interface DeviceStatusResponse {
  device: DeviceSummary;
  battery_charging?: boolean | null;
  last_sample_timestamp?: string | null;
  latest_samples: Record<string, string | null>;
}

export interface DataQualityResponse {
  device_id: number;
  status: FreshnessClass;
  last_successful_sync?: string | null;
  sample_counts_today: Record<string, number>;
  latest_sample_timestamps: Record<string, string | null>;
  sleep_record_present: boolean;
  missing_metrics: string[];
}

export interface DebugResponse {
  device: DeviceSummary;
  table_counts: Record<string, number>;
  recent_syncs: Array<Record<string, string | number | null>>;
}

export interface HealthResponse {
  status: "ok" | "missing_database" | "empty_database";
  db_path: string;
  device_count: number;
}
