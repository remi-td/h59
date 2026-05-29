import { useMemo, useState } from "react";
import type { SleepSessionSummary } from "../api/types";
import { formatShortDate } from "../lib/format";

const STAGE_ORDER = ["deep", "light", "rem", "awake", "unknown"] as const;
const STAGE_COLORS: Record<string, string> = {
  deep: "var(--accent-1)",
  light: "var(--accent-3)",
  rem: "var(--accent-2)",
  awake: "var(--accent-4)",
  unknown: "var(--ink-soft)",
};

type StageKey = (typeof STAGE_ORDER)[number];

type SleepDaySlot = {
  timestamp: string;
  label: string;
  totals: Record<StageKey, number>;
  totalMinutes: number;
};

function buildSevenDaySleepSlots(sessions: SleepSessionSummary[], endDate?: string | null): SleepDaySlot[] {
  const sessionDates = sessions
    .map((session) => session.end_timestamp || session.start_timestamp)
    .filter((value): value is string => Boolean(value));
  const anchor = endDate
    ? new Date(`${endDate}T00:00:00Z`)
    : new Date(Math.max(...sessionDates.map((value) => new Date(value).getTime())));
  if (Number.isNaN(anchor.getTime())) {
    return [];
  }
  const byDay = new Map<string, SleepDaySlot>();
  for (const session of sessions) {
    const stamp = session.end_timestamp || session.start_timestamp;
    if (!stamp) {
      continue;
    }
    const key = stamp.slice(0, 10);
    const existing =
      byDay.get(key) ??
      {
        timestamp: `${key}T00:00:00+00:00`,
        label: formatShortDate(`${key}T00:00:00+00:00`),
        totals: { deep: 0, light: 0, rem: 0, awake: 0, unknown: 0 },
        totalMinutes: 0,
      };
    for (const stage of session.stages) {
      const name = (STAGE_ORDER.includes(stage.stage as StageKey) ? stage.stage : "unknown") as StageKey;
      existing.totals[name] += stage.minutes;
      existing.totalMinutes += stage.minutes;
    }
    byDay.set(key, existing);
  }
  return Array.from({ length: 7 }, (_, index) => {
    const date = new Date(anchor);
    date.setUTCDate(anchor.getUTCDate() - (6 - index));
    const key = date.toISOString().slice(0, 10);
    return (
      byDay.get(key) ?? {
        timestamp: `${key}T00:00:00+00:00`,
        label: formatShortDate(`${key}T00:00:00+00:00`),
        totals: { deep: 0, light: 0, rem: 0, awake: 0, unknown: 0 },
        totalMinutes: 0,
      }
    );
  });
}

function formatMinutes(minutes: number): string {
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return `${hours}h ${String(remainder).padStart(2, "0")}m`;
}

function formatReadout(slot: SleepDaySlot): string {
  if (!slot.totalMinutes) {
    return `${slot.label} · no sleep session`;
  }
  const details = STAGE_ORDER.filter((stage) => slot.totals[stage] > 0)
    .map((stage) => `${stage.toUpperCase()} ${slot.totals[stage]}m`)
    .join(" · ");
  return `${slot.label} · ${formatMinutes(slot.totalMinutes)} · ${details}`;
}

function lastPopulatedIndex(slots: SleepDaySlot[]): number {
  for (let index = slots.length - 1; index >= 0; index -= 1) {
    if (slots[index].totalMinutes > 0) {
      return index;
    }
  }
  return 0;
}

export function SleepStageTrendChart({
  sessions,
  endDate,
}: {
  sessions: SleepSessionSummary[];
  endDate?: string | null;
}) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const slots = useMemo(() => buildSevenDaySleepSlots(sessions, endDate), [sessions, endDate]);

  if (!slots.length) {
    return <div className="panel-empty">No sleep data</div>;
  }

  const width = 760;
  const height = 240;
  const padding = { top: 18, right: 18, bottom: 42, left: 54 };
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;
  const slotWidth = innerWidth / Math.max(slots.length, 1);
  const maxMinutes = Math.max(...slots.map((slot) => slot.totalMinutes), 1);
  const yTicks = Array.from({ length: 4 }, (_, index) => (maxMinutes * index) / 3);
  const activeIndex = hoveredIndex ?? lastPopulatedIndex(slots);
  const active = slots[activeIndex];

  return (
    <section className="chart-panel trend-panel">
      <header className="chart-panel-header">
        <div>
          <h3>Sleep Duration</h3>
          <p className="trend-panel-note">Rolling 7 nights · stacked by stage</p>
        </div>
        <p className="chart-hover-readout">{formatReadout(active)}</p>
      </header>
      <svg viewBox={`0 0 ${width} ${height}`} className="timeseries-chart trend-svg" role="img" aria-label="Rolling 7-day sleep duration">
        <line x1={padding.left} y1={padding.top + innerHeight} x2={width - padding.right} y2={padding.top + innerHeight} className="chart-axis" />
        <line x1={padding.left} y1={padding.top} x2={padding.left} y2={padding.top + innerHeight} className="chart-axis" />
        {yTicks.map((tick) => {
          const y = padding.top + innerHeight - (tick / maxMinutes) * innerHeight;
          return (
            <g key={`tick-${tick.toFixed(2)}`}>
              <line x1={padding.left} y1={y} x2={width - padding.right} y2={y} className="chart-gridline" />
              <text x={padding.left - 10} y={y + 4} textAnchor="end" className="chart-tick">
                {Math.round(tick / 60)}h
              </text>
            </g>
          );
        })}
        <text x={24} y={padding.top + innerHeight / 2} textAnchor="middle" className="chart-axis-label" transform={`rotate(-90 24 ${padding.top + innerHeight / 2})`}>
          Sleep
        </text>
        {slots.map((slot, index) => {
          const x = padding.left + slotWidth * index + slotWidth / 2;
          const barWidth = Math.min(34, slotWidth * 0.38);
          let cursor = padding.top + innerHeight;
          return (
            <g
              key={slot.timestamp}
              onMouseEnter={() => setHoveredIndex(index)}
              onFocus={() => setHoveredIndex(index)}
              onMouseLeave={() => setHoveredIndex(null)}
              onBlur={() => setHoveredIndex(null)}
            >
              <title>{formatReadout(slot)}</title>
              <rect
                x={x - barWidth / 2}
                y={padding.top}
                width={barWidth}
                height={innerHeight}
                rx={barWidth / 2}
                className="trend-bar-rail"
              />
              {STAGE_ORDER.map((stage, stageIndex) => {
                const minutes = slot.totals[stage];
                if (!minutes) {
                  return null;
                }
                const heightValue = (minutes / maxMinutes) * innerHeight;
                cursor -= heightValue;
                const isBase = stageIndex === 0;
                const isTop =
                  STAGE_ORDER.slice(stageIndex + 1).every((nextStage) => slot.totals[nextStage] === 0);
                return (
                  <rect
                    key={`${slot.timestamp}-${stage}`}
                    x={x - barWidth / 2}
                    y={cursor}
                    width={barWidth}
                    height={Math.max(heightValue, 2)}
                    fill={STAGE_COLORS[stage]}
                    opacity={hoveredIndex === null || hoveredIndex === index ? 0.92 : 0.78}
                    rx={isBase || isTop ? barWidth / 2 : 0}
                  />
                );
              })}
              <rect x={x - Math.max(18, barWidth / 2)} y={padding.top} width={Math.max(36, barWidth)} height={innerHeight} fill="transparent" />
              <text x={x} y={height - 16} textAnchor="middle" className="chart-tick">
                {slot.label}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="trend-legend">
        {STAGE_ORDER.filter((stage) => slots.some((slot) => slot.totals[stage] > 0)).map((stage) => (
          <span key={stage} className="trend-legend-item">
            <span className="trend-legend-swatch" style={{ background: STAGE_COLORS[stage] }} />
            <span>{stage.toUpperCase()}</span>
          </span>
        ))}
      </div>
    </section>
  );
}
