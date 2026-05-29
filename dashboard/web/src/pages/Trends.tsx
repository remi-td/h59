import { useMemo } from "react";
import { useTrendData } from "../api/hooks";
import { TrendEChart } from "../components/TrendEChart";
import {
  heartDistributionOption,
  latestHeartSummary,
  latestSleepSummary,
  latestStepsSummary,
  rollingDaySlots,
  sleepStageTrendOption,
  stepsTrendOption,
} from "../components/trend-options";
import { maxTimestamp } from "../lib/series";

export function Trends({ device }: { device: string }) {
  const { data, error, loading } = useTrendData(device);
  const steps = data?.steps ?? null;
  const heart = data?.heart ?? null;
  const sleep = data?.sleep ?? null;

  const endDate = useMemo(() => {
    const latest = maxTimestamp([
      ...(steps?.points || []).map((point) => point.timestamp),
      ...(heart?.points || []).map((point) => point.timestamp),
      ...(sleep?.daily_totals || []).map((point) => point.timestamp),
      ...((sleep?.sessions || []).map((session) => session.end_timestamp || session.start_timestamp || null)),
    ]);
    return latest ? latest.slice(0, 10) : null;
  }, [heart, sleep, steps]);

  const slots = useMemo(() => rollingDaySlots(endDate, 7), [endDate]);
  const stepsChart = useMemo(() => stepsTrendOption(steps?.points || [], slots), [steps, slots]);
  const heartChart = useMemo(() => heartDistributionOption(heart?.points || [], slots), [heart, slots]);
  const sleepChart = useMemo(() => sleepStageTrendOption(sleep?.sessions || [], slots), [sleep, slots]);

  if (error) {
    return <div className="panel-error">{error}</div>;
  }
  if (loading) {
    return <div className="panel-loading">Loading trend views…</div>;
  }

  return (
    <div className="stack-layout">
      <TrendEChart title="Steps" note="Rolling 7 days" summary={latestStepsSummary(steps?.points || [])} option={stepsChart} emptyMessage="No step data" />
      <TrendEChart title="Heart Rate Distribution" note="Rolling 7 days · min, Q1, median, Q3, max" summary={latestHeartSummary(heart?.points || [])} option={heartChart} emptyMessage="No heart-rate distribution data" />
      <TrendEChart title="Sleep Duration" note="Rolling 7 nights · stacked by stage" summary={latestSleepSummary(sleep?.sessions || [])} option={sleepChart} emptyMessage="No sleep data" />
    </div>
  );
}
