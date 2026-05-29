import type {
  DataQualityResponse,
  DebugResponse,
  DeviceStatusResponse,
  DeviceSummary,
  HealthResponse,
  MetricSeriesResponse,
  SleepResponse,
  TodayResponse,
} from "./types";

const API_BASE = import.meta.env.VITE_H59_API_BASE_URL || "";

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
  debug: (device: string) => request<DebugResponse>(`/api/debug?device=${encodeURIComponent(device)}`),
};
