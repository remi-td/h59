import { DependencyList, useEffect, useState } from "react";
import { dashboardApi } from "./client";
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

export type ResourceState<T> = {
  data: T | null;
  error: string | null;
  loading: boolean;
};

function toMessage(reason: unknown): string {
  if (reason instanceof Error) {
    return reason.message;
  }
  return String(reason);
}

export function useApiResource<T>(loader: () => Promise<T>, deps: DependencyList, options?: { resetOnLoad?: boolean }): ResourceState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    if (options?.resetOnLoad) {
      setData(null);
    }
    loader()
      .then((payload) => {
        if (!cancelled) {
          setData(payload);
          setLoading(false);
        }
      })
      .catch((reason: unknown) => {
        if (!cancelled) {
          setError(toMessage(reason));
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, error, loading };
}

export function useBootstrapData() {
  return useApiResource<{ devices: DeviceSummary[]; health: HealthResponse }>(
    async () => {
      const [devices, health] = await Promise.all([dashboardApi.devices(), dashboardApi.health()]);
      return { devices, health };
    },
    [],
  );
}

export function useToday(device: string) {
  return useApiResource<TodayResponse>(() => dashboardApi.today(device), [device], { resetOnLoad: true });
}

export function useMetric(device: string, metric: string, range: string) {
  return useApiResource<MetricSeriesResponse>(() => dashboardApi.metric(metric, device, range), [device, metric, range], { resetOnLoad: true });
}

export function useSleep(device: string, range: string) {
  return useApiResource<SleepResponse>(() => dashboardApi.sleep(device, range), [device, range], { resetOnLoad: true });
}

export function useDeviceData(device: string) {
  return useApiResource<{ status: DeviceStatusResponse; quality: DataQualityResponse }>(
    async () => {
      const [status, quality] = await Promise.all([dashboardApi.deviceStatus(device), dashboardApi.dataQuality(device)]);
      return { status, quality };
    },
    [device],
    { resetOnLoad: true },
  );
}

export function useDebug(device: string) {
  return useApiResource<DebugResponse>(() => dashboardApi.debug(device), [device], { resetOnLoad: true });
}

export function useTrendData(device: string) {
  return useApiResource<{ steps: MetricSeriesResponse; heart: MetricSeriesResponse; sleep: SleepResponse }>(
    async () => {
      const [steps, heart, sleep] = await Promise.all([
        dashboardApi.metric("steps", device, "7d"),
        dashboardApi.metric("heart-rate", device, "7d"),
        dashboardApi.sleep(device, "7d"),
      ]);
      return { steps, heart, sleep };
    },
    [device],
    { resetOnLoad: true },
  );
}

export function useHeartData(device: string) {
  return useApiResource<{ heart: MetricSeriesResponse; hrv: MetricSeriesResponse; sleep: SleepResponse }>(
    async () => {
      const [heart, hrv, sleep] = await Promise.all([
        dashboardApi.metric("heart-rate", device, "24h"),
        dashboardApi.metric("hrv", device, "24h"),
        dashboardApi.sleep(device, "7d"),
      ]);
      return { heart, hrv, sleep };
    },
    [device],
    { resetOnLoad: true },
  );
}

export function useOxygenData(device: string) {
  return useApiResource<{ spo2: MetricSeriesResponse; stress: MetricSeriesResponse; sleep: SleepResponse }>(
    async () => {
      const [spo2, stress, sleep] = await Promise.all([
        dashboardApi.metric("spo2", device, "24h"),
        dashboardApi.metric("stress", device, "24h"),
        dashboardApi.sleep(device, "7d"),
      ]);
      return { spo2, stress, sleep };
    },
    [device],
    { resetOnLoad: true },
  );
}
