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

export function Oxygen({ device }: { device: string }) {
  const [spo2, setSpo2] = useState<MetricSeriesResponse | null>(null);
  const [stress, setStress] = useState<MetricSeriesResponse | null>(null);
  const [sleep, setSleep] = useState<SleepResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      dashboardApi.metric("spo2", device, "24h"),
      dashboardApi.metric("stress", device, "24h"),
      dashboardApi.sleep(device, "7d"),
    ]).then(([spo2Payload, stressPayload, sleepPayload]) => {
      if (!cancelled) {
        setSpo2(spo2Payload);
        setStress(stressPayload);
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
        ...(spo2?.points || []).map((point) => point.timestamp),
        ...(stress?.points || []).map((point) => point.timestamp),
      ]),
    [spo2, stress],
  );

  return (
    <div className="stack-layout">
      <TimeSeriesChart points={spo2?.points || []} title="SpO₂, Last 24 Hours" color="var(--accent-1)" unit={spo2?.unit || "%"} yAxisLabel="SpO₂ (%)" xAxisLabel="Time" sleepSessions={sleep?.sessions || []} shadeSleep rangeHours={24} rangeEnd={rangeEnd} />
      <TimeSeriesChart points={stress?.points || []} title="Stress, Last 24 Hours" color="var(--accent-3)" unit={stress?.unit || "score"} yAxisLabel="Stress score" xAxisLabel="Time" sleepSessions={sleep?.sessions || []} shadeSleep rangeHours={24} rangeEnd={rangeEnd} />
    </div>
  );
}
