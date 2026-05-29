import { useEffect, useMemo, useState } from "react";
import { dashboardApi } from "../api/client";
import type { MetricSeriesResponse, SleepResponse } from "../api/types";
import { TimeSeriesChart } from "../components/TimeSeriesChart";

function maxTimestamp(values: Array<string | null | undefined>): string | null {
  const timestamps = values.filter((value): value is string => Boolean(value));
  if (!timestamps.length) {
    return null;
  }
  return timestamps.reduce((latest, current) => (current > latest ? current : latest));
}

export function Heart({ device }: { device: string }) {
  const [heart, setHeart] = useState<MetricSeriesResponse | null>(null);
  const [hrv, setHrv] = useState<MetricSeriesResponse | null>(null);
  const [sleep, setSleep] = useState<SleepResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      dashboardApi.metric("heart-rate", device, "24h"),
      dashboardApi.metric("hrv", device, "24h"),
      dashboardApi.sleep(device, "7d"),
    ]).then(([heartPayload, hrvPayload, sleepPayload]) => {
      if (!cancelled) {
        setHeart(heartPayload);
        setHrv(hrvPayload);
        setSleep(sleepPayload);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [device]);

  const rangeEnd = useMemo(
    () =>
      maxTimestamp([
        ...(heart?.points || []).map((point) => point.timestamp),
        ...(hrv?.points || []).map((point) => point.timestamp),
      ]),
    [heart, hrv],
  );

  return (
    <div className="stack-layout">
      <TimeSeriesChart points={heart?.points || []} title="Heart Rate, Last 24 Hours" color="var(--accent-4)" unit={heart?.unit || "bpm"} yAxisLabel="Heart rate (bpm)" xAxisLabel="Time" sleepSessions={sleep?.sessions || []} shadeSleep rangeHours={24} rangeEnd={rangeEnd} />
      <TimeSeriesChart points={hrv?.points || []} title="HRV, Last 24 Hours" color="var(--accent-2)" unit={hrv?.unit || "ms"} yAxisLabel="HRV (ms)" xAxisLabel="Time" sleepSessions={sleep?.sessions || []} shadeSleep rangeHours={24} rangeEnd={rangeEnd} />
    </div>
  );
}
