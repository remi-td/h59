import { useEffect, useState } from "react";
import { dashboardApi } from "../api/client";
import type { TodayResponse } from "../api/types";
import { MetricCard } from "../components/MetricCard";

export function Today({ device, onReportDateChange }: { device: string; onReportDateChange?: (value: string | null) => void }) {
  const [data, setData] = useState<TodayResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    dashboardApi
      .today(device)
      .then((payload) => {
        if (!cancelled) {
          setData(payload);
          onReportDateChange?.(payload.date);
        }
      })
      .catch((reason: Error) => {
        if (!cancelled) {
          setError(reason.message);
        }
      });
    return () => {
      cancelled = true;
      onReportDateChange?.(null);
    };
  }, [device, onReportDateChange]);

  if (error) {
    return <div className="panel-error">{error}</div>;
  }
  if (!data) {
    return <div className="panel-loading">Loading today’s view…</div>;
  }
  return (
    <div className="page-grid">
      {data.cards.map((card) => (
        <MetricCard key={card.id} card={card} />
      ))}
    </div>
  );
}
