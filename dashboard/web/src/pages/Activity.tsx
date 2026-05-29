import { useEffect, useState } from "react";
import { dashboardApi } from "../api/client";
import type { MetricSeriesResponse } from "../api/types";
import { DailyBars } from "../components/DailyBars";

export function Activity({ device }: { device: string }) {
  const [steps, setSteps] = useState<MetricSeriesResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    dashboardApi.metric("steps", device, "30d").then((payload) => {
      if (!cancelled) {
        setSteps(payload);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [device]);

  return (
    <div className="stack-layout">
      <DailyBars points={steps?.points || []} title="30-Day Steps" color="var(--accent-2)" unit={steps?.unit || "steps"} yAxisLabel="Steps" xAxisLabel="Day" />
    </div>
  );
}
