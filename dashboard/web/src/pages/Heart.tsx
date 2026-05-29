import { useMemo } from "react";
import { useHeartData } from "../api/hooks";
import { TimeSeriesChart } from "../components/TimeSeriesChart";
import { maxTimestamp } from "../lib/series";

export function Heart({ device }: { device: string }) {
  const { data, error, loading } = useHeartData(device);
  const heart = data?.heart ?? null;
  const hrv = data?.hrv ?? null;
  const sleep = data?.sleep ?? null;

  const rangeEnd = useMemo(
    () =>
      maxTimestamp([
        ...(heart?.points || []).map((point) => point.timestamp),
        ...(hrv?.points || []).map((point) => point.timestamp),
      ]),
    [heart, hrv],
  );

  if (error) {
    return <div className="panel-error">{error}</div>;
  }
  if (loading) {
    return <div className="panel-loading">Loading heart metrics…</div>;
  }

  return (
    <div className="stack-layout">
      <TimeSeriesChart points={heart?.points || []} title="Heart Rate, Last 24 Hours" color="var(--accent-4)" unit={heart?.unit || "bpm"} yAxisLabel="Heart rate (bpm)" xAxisLabel="Time" sleepSessions={sleep?.sessions || []} shadeSleep rangeHours={24} rangeEnd={rangeEnd} />
      <TimeSeriesChart points={hrv?.points || []} title="HRV, Last 24 Hours" color="var(--accent-2)" unit={hrv?.unit || "ms"} yAxisLabel="HRV (ms)" xAxisLabel="Time" sleepSessions={sleep?.sessions || []} shadeSleep rangeHours={24} rangeEnd={rangeEnd} />
    </div>
  );
}
