import { useEffect } from "react";
import { useToday } from "../api/hooks";
import { MetricCard } from "../components/MetricCard";

export function Today({ device, onReportDateChange }: { device: string; onReportDateChange?: (value: string | null) => void }) {
  const { data, error, loading } = useToday(device);

  useEffect(() => {
    onReportDateChange?.(data?.date ?? null);
    return () => {
      onReportDateChange?.(null);
    };
  }, [data?.date, onReportDateChange]);

  if (error) {
    return <div className="panel-error">{error}</div>;
  }
  if (loading || !data) {
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
