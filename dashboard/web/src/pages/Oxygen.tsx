import { useOxygenData } from "../api/hooks";
import { TimeSeriesChart } from "../components/TimeSeriesChart";

export function Oxygen({ device }: { device: string }) {
  const { data, error, loading } = useOxygenData(device);
  const spo2 = data?.spo2 ?? null;
  const stress = data?.stress ?? null;
  const sleep = data?.sleep ?? null;
  const rangeEnd = new Date().toISOString();

  if (error) {
    return <div className="panel-error">{error}</div>;
  }
  if (loading) {
    return <div className="panel-loading">Loading oxygen metrics…</div>;
  }

  return (
    <div className="stack-layout">
      <TimeSeriesChart points={spo2?.points || []} title="SpO₂, Last 24 Hours" color="var(--accent-1)" unit={spo2?.unit || "%"} yAxisLabel="SpO₂ (%)" xAxisLabel="Time" sleepSessions={sleep?.sessions || []} shadeSleep rangeHours={24} rangeEnd={rangeEnd} />
      <TimeSeriesChart points={stress?.points || []} title="Stress, Last 24 Hours" color="var(--accent-3)" unit={stress?.unit || "score"} yAxisLabel="Stress score" xAxisLabel="Time" sleepSessions={sleep?.sessions || []} shadeSleep rangeHours={24} rangeEnd={rangeEnd} />
    </div>
  );
}
