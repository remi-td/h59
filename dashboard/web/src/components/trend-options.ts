import type { EChartsOption } from "echarts";
import type { MetricPoint, SleepSessionSummary } from "../api/types";
import { formatShortDate } from "../lib/format";
import { SLEEP_STAGE_COLORS } from "../lib/sleep-stage-colors";

export const STAGE_ORDER = ["deep", "light", "rem", "awake", "unknown"] as const;

export type DaySlot = {
  key: string;
  timestamp: string;
  label: string;
};

function lastNonNullIndex(values: Array<number | null>, predicate: (value: number | null) => boolean): number {
  for (let index = values.length - 1; index >= 0; index -= 1) {
    if (predicate(values[index])) {
      return index;
    }
  }
  return -1;
}

export function rollingDaySlots(endDate: string | null, days: number): DaySlot[] {
  const anchor = new Date(`${endDate ?? new Date().toISOString().slice(0, 10)}T00:00:00Z`);
  return Array.from({ length: days }, (_, index) => {
    const value = new Date(anchor);
    value.setUTCDate(anchor.getUTCDate() - (days - 1 - index));
    const key = value.toISOString().slice(0, 10);
    return {
      key,
      timestamp: `${key}T00:00:00+00:00`,
      label: formatShortDate(`${key}T00:00:00+00:00`),
    };
  });
}

function baseGrid(): EChartsOption["grid"] {
  return { left: 62, right: 28, top: 18, bottom: 44, containLabel: false };
}

function axisStyles(): Pick<EChartsOption, "xAxis" | "yAxis"> {
  return {
    xAxis: {
      type: "category",
      axisTick: { show: false },
      axisLine: { lineStyle: { color: "rgba(31, 38, 34, 0.14)" } },
      axisLabel: { color: "#68756a", fontSize: 13, margin: 14 },
    },
    yAxis: {
      type: "value",
      axisTick: { show: false },
      axisLine: { show: false },
      splitLine: { lineStyle: { color: "rgba(31, 38, 34, 0.12)", type: "dashed" } },
      axisLabel: { color: "#68756a", fontSize: 13, margin: 14 },
      nameLocation: "middle",
      nameGap: 50,
      nameTextStyle: { color: "#68756a", fontSize: 14, fontWeight: 600 },
    },
  };
}

export function stepsTrendOption(points: MetricPoint[], slots: DaySlot[], xAxisLabel = "Day"): EChartsOption | null {
  const pointMap = new Map(points.map((point) => [point.timestamp.slice(0, 10), Number(point.value ?? 0)]));
  const values = slots.map((slot) => pointMap.get(slot.key) ?? null);
  const latestIndex = lastNonNullIndex(values, (value) => value !== null);
  const latestValue = latestIndex >= 0 ? values[latestIndex] : null;
  const maxValue = Math.max(...values.map((value) => value ?? 0), 1000);
  if (latestValue === null && values.every((value) => value === null)) {
    return null;
  }
  return {
    animation: false,
    grid: baseGrid(),
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "line", lineStyle: { color: "var(--line-strong)" } },
      backgroundColor: "var(--tooltip-background)",
      borderColor: "var(--tooltip-border)",
      textStyle: { color: "var(--ink)" },
      formatter: (params: any) => {
        const point = Array.isArray(params) ? params[0] : params;
        if (!point || point.value === null || point.value === undefined || point.value === "-") {
          return `${point?.axisValueLabel ?? ""}<br/>No activity summary`;
        }
        return `${point.axisValueLabel}<br/><strong>${new Intl.NumberFormat().format(Number(point.value))} steps</strong>`;
      },
    },
    xAxis: {
      ...(axisStyles().xAxis as object),
      data: slots.map((slot) => slot.label),
      name: xAxisLabel,
      nameLocation: "middle",
      nameGap: 34,
      nameTextStyle: { color: "#68756a", fontSize: 14, fontWeight: 600 },
    },
    yAxis: {
      ...(axisStyles().yAxis as object),
      name: "Steps",
      min: 0,
      max: maxValue,
      axisLabel: {
        color: "#68756a",
        fontSize: 13,
        formatter: (value: number) => (value >= 1000 ? `${Math.round(value / 1000)}k` : `${value}`),
      },
    },
    series: [
      {
        type: "line",
        smooth: 0.25,
        data: values,
        symbol: "none",
        connectNulls: false,
        lineStyle: { width: 3, color: "var(--accent-2)" },
        itemStyle: { color: "var(--accent-2)" },
        areaStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: "rgba(var(--accent-2-rgb), 0.26)" },
              { offset: 1, color: "rgba(var(--accent-2-rgb), 0.02)" },
            ],
          },
        },
      },
    ],
  };
}

export function heartDistributionOption(points: MetricPoint[], slots: DaySlot[]): EChartsOption | null {
  const pointMap = new Map(points.map((point) => [point.timestamp.slice(0, 10), point]));
  const data = slots.map((slot) => {
    const point = pointMap.get(slot.key);
    if (!point || point.min_value === null || point.lower_quartile === null || point.median_value === null || point.upper_quartile === null || point.max_value === null) {
      return [NaN, NaN, NaN, NaN, NaN];
    }
    return [
      Number(point.min_value),
      Number(point.lower_quartile),
      Number(point.median_value),
      Number(point.upper_quartile),
      Number(point.max_value),
    ];
  });
  const latest = [...points].reverse().find((point) => point.median_value !== null && point.median_value !== undefined) ?? null;
  if (!latest && data.every((row) => row.every((value) => Number.isNaN(value)))) {
    return null;
  }
  return {
    animation: false,
    grid: baseGrid(),
    tooltip: {
      trigger: "item",
      backgroundColor: "var(--tooltip-background)",
      borderColor: "var(--tooltip-border)",
      textStyle: { color: "var(--ink)" },
      formatter: (param: any) => {
        const value = param.data as number[];
        if (!value || Number.isNaN(value[0])) {
          return `${param.name}<br/>No heart-rate distribution`;
        }
        return `${param.name}<br/>min ${value[0]} bpm<br/>q1 ${value[1]} bpm<br/>median ${value[2]} bpm<br/>q3 ${value[3]} bpm<br/>max ${value[4]} bpm`;
      },
    },
    xAxis: {
      ...(axisStyles().xAxis as object),
      data: slots.map((slot) => slot.label),
      name: "Day",
      nameLocation: "middle",
      nameGap: 34,
      nameTextStyle: { color: "#68756a", fontSize: 14, fontWeight: 600 },
    },
    yAxis: {
      ...(axisStyles().yAxis as object),
      name: "Heart rate (bpm)",
      min: "dataMin",
      max: "dataMax",
    },
    series: [
      {
        type: "boxplot",
        data,
        itemStyle: {
          color: "rgba(var(--accent-4-rgb), 0.72)",
          borderColor: "var(--accent-4)",
          borderWidth: 1.2,
        },
        emphasis: {
          itemStyle: {
            color: "rgba(var(--accent-4-rgb), 0.84)",
          },
        },
      },
    ],
  };
}

export function sleepStageTrendOption(sessions: SleepSessionSummary[], slots: DaySlot[], xAxisLabel = "Night"): EChartsOption | null {
  const byDay = new Map<string, Record<string, number>>();
  for (const session of sessions) {
    const stamp = session.end_timestamp || session.start_timestamp;
    if (!stamp) {
      continue;
    }
    const key = stamp.slice(0, 10);
    const bucket = byDay.get(key) ?? { deep: 0, light: 0, rem: 0, awake: 0, unknown: 0 };
    for (const stage of session.stages) {
      const name = STAGE_ORDER.includes(stage.stage as (typeof STAGE_ORDER)[number]) ? stage.stage : "unknown";
      bucket[name] += stage.minutes;
    }
    byDay.set(key, bucket);
  }

  const series = STAGE_ORDER.map((stage) => ({
    name: stage.toUpperCase(),
    type: "bar" as const,
    stack: "sleep",
    barWidth: 28,
    itemStyle: { color: SLEEP_STAGE_COLORS[stage], borderRadius: [6, 6, 0, 0] },
    emphasis: { focus: "series" as const },
    data: slots.map((slot) => byDay.get(slot.key)?.[stage] ?? 0),
  }));

  const totals = slots.map((slot) => STAGE_ORDER.reduce((sum, stage) => sum + (byDay.get(slot.key)?.[stage] ?? 0), 0));
  const latestIndex = lastNonNullIndex(totals, (value) => (value ?? 0) > 0);
  if (latestIndex < 0) {
    return null;
  }
  const maxValue = Math.max(...totals, 60);
  return {
    animation: false,
    grid: { ...baseGrid(), top: 42 },
    legend: {
      top: 0,
      right: 0,
      icon: "roundRect",
      itemWidth: 10,
      itemHeight: 10,
      textStyle: { color: "#68756a", fontSize: 12 },
    },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      backgroundColor: "var(--tooltip-background)",
      borderColor: "var(--tooltip-border)",
      textStyle: { color: "var(--ink)" },
      formatter: (params: any) => {
        const items = Array.isArray(params) ? params : [params];
        const total = items.reduce((sum, item) => sum + Number(item.value || 0), 0);
        if (!total) {
          return `${items[0]?.axisValueLabel ?? ""}<br/>No sleep session`;
        }
        const details = items
          .filter((item) => Number(item.value) > 0)
          .map((item) => `${item.marker}${item.seriesName}: ${item.value} min`)
          .join("<br/>");
        return `${items[0].axisValueLabel}<br/><strong>${Math.floor(total / 60)}h ${String(total % 60).padStart(2, "0")}m</strong><br/>${details}`;
      },
    },
    xAxis: {
      ...(axisStyles().xAxis as object),
      data: slots.map((slot) => slot.label),
      name: xAxisLabel,
      nameLocation: "middle",
      nameGap: 34,
      nameTextStyle: { color: "#68756a", fontSize: 14, fontWeight: 600 },
    },
    yAxis: {
      ...(axisStyles().yAxis as object),
      name: "Sleep",
      min: 0,
      max: maxValue,
      axisLabel: {
        color: "#68756a",
        fontSize: 13,
        formatter: (value: number) => `${Math.round(value / 60)}h`,
      },
    },
    series,
  };
}

export function latestStepsSummary(points: MetricPoint[]): string | null {
  const latest = [...points].reverse().find((point) => point.value !== null && point.value !== undefined);
  if (!latest || latest.value === null || latest.value === undefined) {
    return null;
  }
  return `${formatShortDate(latest.timestamp)} · ${new Intl.NumberFormat().format(Number(latest.value))} steps`;
}

export function latestHeartSummary(points: MetricPoint[]): string | null {
  const latest = [...points].reverse().find((point) => point.median_value !== null && point.median_value !== undefined);
  if (!latest) {
    return null;
  }
  return `${formatShortDate(latest.timestamp)} · min ${latest.min_value} bpm · q1 ${latest.lower_quartile} bpm · med ${latest.median_value} bpm · q3 ${latest.upper_quartile} bpm · max ${latest.max_value} bpm`;
}

export function latestSleepSummary(sessions: SleepSessionSummary[]): string | null {
  const latest = sessions[0];
  if (!latest) {
    return null;
  }
  const total = latest.total_minutes ?? latest.stages.reduce((sum, stage) => sum + stage.minutes, 0);
  const details = STAGE_ORDER.map((stage) => {
    const minutes = latest.stages.filter((item) => item.stage === stage).reduce((sum, item) => sum + item.minutes, 0);
    return minutes > 0 ? `${stage.toUpperCase()} ${minutes}m` : null;
  }).filter(Boolean);
  return `${formatShortDate(latest.end_timestamp || latest.start_timestamp || "")} · ${Math.floor(total / 60)}h ${String(total % 60).padStart(2, "0")}m${details.length ? ` · ${details.join(" · ")}` : ""}`;
}
