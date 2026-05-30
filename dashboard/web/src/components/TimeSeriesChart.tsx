import ReactECharts from "echarts-for-react";
import type { EChartsOption } from "echarts";
import { useMemo } from "react";
import type { MetricPoint, SleepSessionSummary } from "../api/types";

function metricValue(point: MetricPoint): number | null {
  if (point.value !== null && point.value !== undefined) {
    return Number(point.value);
  }
  if (point.max_value !== null && point.max_value !== undefined) {
    return Number(point.max_value);
  }
  if (point.min_value !== null && point.min_value !== undefined) {
    return Number(point.min_value);
  }
  return null;
}

function formatMetricPoint(point: MetricPoint, unit?: string | null): string {
  const stamp = new Date(point.timestamp).toLocaleString();
  const values: string[] = [];
  if (point.value !== null && point.value !== undefined) {
    values.push(`${Number(point.value).toFixed(Number.isInteger(point.value) ? 0 : 1)}${unit ? ` ${unit}` : ""}`);
  }
  if (point.min_value !== null && point.min_value !== undefined) {
    values.push(`min ${Number(point.min_value).toFixed(1)}${unit ? ` ${unit}` : ""}`);
  }
  if (point.max_value !== null && point.max_value !== undefined) {
    values.push(`max ${Number(point.max_value).toFixed(1)}${unit ? ` ${unit}` : ""}`);
  }
  return `${stamp} · ${values.join(" · ") || "n/a"}`;
}

function areaColorFor(lineColor: string): string {
  if (lineColor === "var(--accent-2)") {
    return "rgba(var(--accent-2-rgb), 0.20)";
  }
  if (lineColor === "var(--accent-3)") {
    return "rgba(var(--accent-3-rgb), 0.20)";
  }
  if (lineColor === "var(--accent-4)") {
    return "rgba(var(--accent-4-rgb), 0.20)";
  }
  return "rgba(var(--accent-1-rgb), 0.20)";
}

function toTimestamp(value: string | null | undefined): number | null {
  if (!value) {
    return null;
  }
  const parsed = new Date(value).getTime();
  return Number.isNaN(parsed) ? null : parsed;
}

function buildSleepBands(sleepSessions: SleepSessionSummary[] | undefined, pointRange: [number, number] | null) {
  if (!sleepSessions?.length || !pointRange) {
    return [];
  }
  return sleepSessions
    .map((session) => {
      const start = session.start_timestamp ? new Date(session.start_timestamp).getTime() : NaN;
      const end = session.end_timestamp ? new Date(session.end_timestamp).getTime() : NaN;
      if (Number.isNaN(start) || Number.isNaN(end)) {
        return null;
      }
      if (end < pointRange[0] || start > pointRange[1]) {
        return null;
      }
      return [
        { xAxis: Math.max(start, pointRange[0]) },
        { xAxis: Math.min(end, pointRange[1]) },
      ];
    })
    .filter((band): band is [{ xAxis: number }, { xAxis: number }] => band !== null);
}

export function TimeSeriesChart({
  points,
  color = "var(--accent-1)",
  title,
  unit,
  yAxisLabel = "Value",
  xAxisLabel = "Time",
  sleepSessions,
  shadeSleep = false,
  rangeHours,
  rangeEnd,
}: {
  points: MetricPoint[];
  color?: string;
  title?: string;
  unit?: string | null;
  yAxisLabel?: string;
  xAxisLabel?: string;
  sleepSessions?: SleepSessionSummary[];
  shadeSleep?: boolean;
  rangeHours?: number;
  rangeEnd?: string | null;
}) {
  const plottedPoints = useMemo(
    () =>
      points
        .map((point) => ({ point, value: metricValue(point) }))
        .filter((entry): entry is { point: MetricPoint; value: number } => entry.value !== null),
    [points],
  );

  const latest = plottedPoints[plottedPoints.length - 1];
  const latestPointTime = latest ? toTimestamp(latest.point.timestamp) : null;
  const explicitRangeEnd = toTimestamp(rangeEnd);
  const resolvedRangeEnd = explicitRangeEnd ?? latestPointTime;
  const resolvedRangeStart =
    resolvedRangeEnd !== null && rangeHours
      ? resolvedRangeEnd - rangeHours * 60 * 60 * 1000
      : plottedPoints.length > 1
        ? toTimestamp(plottedPoints[0].point.timestamp)
        : latestPointTime;
  const pointRange =
    resolvedRangeStart !== null && resolvedRangeEnd !== null
      ? [resolvedRangeStart, resolvedRangeEnd] as [number, number]
      : null;
  const sleepBands = buildSleepBands(sleepSessions, pointRange);

  const option = useMemo<EChartsOption | null>(() => {
    if (!plottedPoints.length) {
      return null;
    }

    return {
      animation: false,
      grid: { left: 70, right: 24, top: 18, bottom: 54 },
      tooltip: {
      trigger: "axis",
      axisPointer: { type: "line", lineStyle: { color: "var(--line-strong)" } },
      backgroundColor: "var(--tooltip-background)",
      borderColor: "var(--tooltip-border)",
      textStyle: { color: "var(--ink)" },
        confine: true,
        extraCssText: "max-width: 280px; white-space: normal; box-shadow: 0 12px 28px rgba(31, 38, 34, 0.12);",
        position: (point: number[], _params: unknown, _dom: unknown, _rect: unknown, size: { contentSize: number[]; viewSize: number[] }) => {
          const [x, y] = point;
          const [contentWidth, contentHeight] = size.contentSize;
          const [viewWidth, viewHeight] = size.viewSize;
          const left = Math.min(Math.max(12, x + 16), Math.max(12, viewWidth - contentWidth - 12));
          const top = y > viewHeight / 2
            ? Math.max(12, y - contentHeight - 16)
            : Math.min(viewHeight - contentHeight - 12, y + 16);
          return [left, top];
        },
        formatter: (params: any) => {
          const point = Array.isArray(params) ? params[0] : params;
          const matched = plottedPoints.find((entry) => new Date(entry.point.timestamp).getTime() === point.value?.[0]);
          if (!matched) {
            return "No data";
          }
          return formatMetricPoint(matched.point, unit);
        },
      },
      xAxis: {
        type: "time",
        min: pointRange?.[0],
        max: pointRange?.[1],
        name: xAxisLabel,
        nameLocation: "middle",
        nameGap: 34,
        nameTextStyle: { color: "#68756a", fontSize: 14, fontWeight: 600 },
        axisTick: { show: false },
        axisLine: { lineStyle: { color: "rgba(31, 38, 34, 0.14)" } },
        axisLabel: { color: "#68756a", fontSize: 13 },
        splitLine: { show: false },
      },
      yAxis: {
        type: "value",
        name: yAxisLabel,
        nameLocation: "middle",
        nameGap: 54,
        nameTextStyle: { color: "#68756a", fontSize: 14, fontWeight: 600 },
        axisTick: { show: false },
        axisLine: { show: false },
        axisLabel: { color: "#68756a", fontSize: 13 },
        splitLine: { lineStyle: { color: "rgba(31, 38, 34, 0.12)", type: "dashed" } },
        scale: true,
      },
      series: [
        {
          type: "line",
          smooth: 0.22,
          showSymbol: false,
          symbol: "none",
          data: plottedPoints.map((entry) => [new Date(entry.point.timestamp).getTime(), entry.value]),
          lineStyle: { width: 3, color },
          itemStyle: { color },
          areaStyle: {
            color: {
              type: "linear",
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: areaColorFor(color) },
                { offset: 1, color: "rgba(255, 250, 242, 0.02)" },
              ],
            },
          },
          markArea:
            shadeSleep && sleepBands.length
              ? {
                  silent: true,
                  itemStyle: { color: "rgba(var(--accent-1-rgb), 0.08)" },
                  data: sleepBands,
                }
              : undefined,
        },
      ],
    };
  }, [color, plottedPoints, pointRange, shadeSleep, sleepBands, unit, xAxisLabel, yAxisLabel]);

  if (!option || !latest) {
    return <div className="panel-empty">No series data</div>;
  }

  return (
    <section className="chart-panel trend-panel">
      {title ? (
        <header className="chart-panel-header">
          <h3>{title}</h3>
          <p className="chart-hover-readout">{formatMetricPoint(latest.point, unit)}</p>
        </header>
      ) : null}
      <ReactECharts option={option} opts={{ renderer: "svg" }} notMerge lazyUpdate className="trend-echart" style={{ height: 280 }} />
    </section>
  );
}
