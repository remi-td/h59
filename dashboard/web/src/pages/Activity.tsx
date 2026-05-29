import { useMemo } from "react";
import { useMetric } from "../api/hooks";
import { TrendEChart } from "../components/TrendEChart";
import { latestStepsSummary, rollingDaySlots, stepsTrendOption } from "../components/trend-options";

export function Activity({ device }: { device: string }) {
  const { data, error, loading } = useMetric(device, "steps", "30d");

  const endDate = useMemo(() => data?.points[data.points.length - 1]?.timestamp.slice(0, 10) ?? null, [data]);
  const slots = useMemo(() => rollingDaySlots(endDate, 30), [endDate]);
  const option = useMemo(() => stepsTrendOption(data?.points || [], slots), [data, slots]);

  if (error) {
    return <div className="panel-error">{error}</div>;
  }
  if (loading) {
    return <div className="panel-loading">Loading activity trends…</div>;
  }

  return (
    <div className="stack-layout">
      <TrendEChart title="Steps" note="Rolling 30 days" summary={latestStepsSummary(data?.points || [])} option={option} emptyMessage="No activity data" />
    </div>
  );
}
