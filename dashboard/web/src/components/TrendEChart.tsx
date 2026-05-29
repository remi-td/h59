import ReactECharts from "echarts-for-react";
import type { EChartsOption } from "echarts";

export function TrendEChart({
  title,
  note,
  summary,
  option,
  emptyMessage = "No data",
  onEvents,
}: {
  title: string;
  note: string;
  summary?: string | null;
  option?: EChartsOption | null;
  emptyMessage?: string;
  onEvents?: Record<string, (params: unknown) => void>;
}) {
  if (!option) {
    return <div className="panel-empty">{emptyMessage}</div>;
  }

  return (
    <section className="chart-panel trend-panel">
      <header className="chart-panel-header">
        <div>
          <h3>{title}</h3>
          <p className="trend-panel-note">{note}</p>
        </div>
        {summary ? <p className="chart-hover-readout">{summary}</p> : null}
      </header>
      <ReactECharts option={option} onEvents={onEvents} opts={{ renderer: "svg" }} notMerge lazyUpdate className="trend-echart" style={{ height: 280 }} />
    </section>
  );
}
