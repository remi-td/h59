import type {
  CurrentInsightResponse,
  DailyFeaturesResponse,
  DataQualityResponse,
  DebugResponse,
  DeviceStatusResponse,
  FeatureSeriesResponse,
  DeviceSummary,
  HealthResponse,
  MetricCatalogResponse,
  MetricSeriesResponse,
  SleepResponse,
  TodayResponse,
} from "./types";

const API_BASE = import.meta.env.VITE_H59_API_BASE_URL || "";

function queryString(params: Record<string, string | number | boolean | string[] | undefined | null>): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null) return;
    if (Array.isArray(value)) {
      value.forEach((item) => search.append(key, item));
    } else {
      search.set(key, String(value));
    }
  });
  const rendered = search.toString();
  return rendered ? `?${rendered}` : "";
}

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const dashboardApi = {
  health: () => request<HealthResponse>("/api/health"),
  devices: () => request<DeviceSummary[]>("/api/devices"),
  today: (device: string) => request<TodayResponse>(`/api/today?device=${encodeURIComponent(device)}`),
  metric: (metric: string, device: string, range: string) =>
    request<MetricSeriesResponse>(`/api/metrics/${metric}?device=${encodeURIComponent(device)}&range=${encodeURIComponent(range)}`),
  sleep: (device: string, range: string) =>
    request<SleepResponse>(`/api/sleep?device=${encodeURIComponent(device)}&range=${encodeURIComponent(range)}`),
  deviceStatus: (device: string) =>
    request<DeviceStatusResponse>(`/api/device/status?device=${encodeURIComponent(device)}`),
  dataQuality: (device: string) =>
    request<DataQualityResponse>(`/api/data-quality?device=${encodeURIComponent(device)}`),
  currentInsight: (device: string) =>
    request<CurrentInsightResponse>(`/api/insights/current?device=${encodeURIComponent(device)}`),
  metricCatalog: () => request<MetricCatalogResponse>("/api/metrics/catalog"),
  features: (device: string, metrics: string[], includeBaseline = true, from?: string, to?: string) =>
    request<FeatureSeriesResponse>(
      `/api/features${queryString({ device, metric_key: metrics, include_baseline: includeBaseline, from, to })}`,
    ),
  dailyFeatures: (device: string, date?: string) =>
    request<DailyFeaturesResponse>(`/api/features/daily${queryString({ device, date })}`),
  debug: (device: string) => request<DebugResponse>(`/api/debug?device=${encodeURIComponent(device)}`),
};
