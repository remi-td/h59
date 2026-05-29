import { useMemo, useState } from "react";
import type { MetricPoint } from "../api/types";
import { formatShortDate } from "../lib/format";

type DaySlot = {
  timestamp: string;
  label: string;
  value: number | null;
};

function dayKey(value: string): string {
  return value.slice(0, 10);
}

function buildSevenDaySlots(points: MetricPoint[], endDate?: string | null): DaySlot[] {
  const anchor = endDate ? new Date(`${endDate}T00:00:00Z`) : new Date(Math.max(...points.map((point) => new Date(point.timestamp).getTime())));
  if (Number.isNaN(anchor.getTime())) {
    return [];
  }
  const values = new Map<string, number>();
  for (const point of points) {
    const key = dayKey(point.timestamp);
    if (point.value !== null && point.value !== undefined) {
      values.set(key, Number(point.value));
    }
  }
  return Array.from({ length: 7 }, (_, index) => {
    const date = new Date(anchor);
    date.setUTCDate(anchor.getUTCDate() - (6 - index));
    const key = date.toISOString().slice(0, 10);
    return {
      timestamp: `${key}T00:00:00+00:00`,
      label: formatShortDate(`${key}T00:00:00+00:00`),
      value: values.get(key) ?? null,
    };
  });
}

function formatTick(value: number): string {
  if (value >= 1000) {
    return `${Math.round(value / 1000)}k`;
  }
  return value.toFixed(0);
}

function formatReadout(slot: DaySlot): string {
  if (slot.value === null) {
    return `${slot.label} · no activity summary`;
  }
  return `${slot.label} · ${new Intl.NumberFormat().format(slot.value)} steps`;
}

function lastPopulatedIndex(slots: DaySlot[]): number {
  for (let index = slots.length - 1; index >= 0; index -= 1) {
    if (slots[index].value !== null) {
      return index;
    }
  }
  return 0;
}

export function StepsTrendChart({
  points,
  endDate,
}: {
  points: MetricPoint[];
  endDate?: string | null;
}) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const slots = useMemo(() => buildSevenDaySlots(points, endDate), [points, endDate]);

  if (!slots.length) {
    return <div className="panel-empty">No step data</div>;
  }

  const width = 760;
  const height = 240;
  const padding = { top: 18, right: 18, bottom: 42, left: 54 };
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;
  const slotWidth = innerWidth / Math.max(slots.length, 1);
  const maxValue = Math.max(...slots.map((slot) => slot.value ?? 0), 1);
  const yTicks = Array.from({ length: 4 }, (_, index) => (maxValue * index) / 3);
  const activeIndex = hoveredIndex ?? lastPopulatedIndex(slots);
  const active = slots[activeIndex];

  return (
    <section className="chart-panel trend-panel">
      <header className="chart-panel-header">
        <div>
          <h3>Steps</h3>
          <p className="trend-panel-note">Rolling 7 days</p>
        </div>
        <p className="chart-hover-readout">{formatReadout(active)}</p>
      </header>
      <svg viewBox={`0 0 ${width} ${height}`} className="timeseries-chart trend-svg" role="img" aria-label="Rolling 7-day steps">
        <line x1={padding.left} y1={padding.top + innerHeight} x2={width - padding.right} y2={padding.top + innerHeight} className="chart-axis" />
        <line x1={padding.left} y1={padding.top} x2={padding.left} y2={padding.top + innerHeight} className="chart-axis" />
        {yTicks.map((tick) => {
          const y = padding.top + innerHeight - (tick / maxValue) * innerHeight;
          return (
            <g key={`tick-${tick.toFixed(2)}`}>
              <line x1={padding.left} y1={y} x2={width - padding.right} y2={y} className="chart-gridline" />
              <text x={padding.left - 10} y={y + 4} textAnchor="end" className="chart-tick">
                {formatTick(tick)}
              </text>
            </g>
          );
        })}
        <text x={24} y={padding.top + innerHeight / 2} textAnchor="middle" className="chart-axis-label" transform={`rotate(-90 24 ${padding.top + innerHeight / 2})`}>
          Steps
        </text>
        {slots.map((slot, index) => {
          const x = padding.left + slotWidth * index + slotWidth / 2;
          const barWidth = Math.min(34, slotWidth * 0.38);
          const value = slot.value ?? 0;
          const filledHeight = (value / maxValue) * innerHeight;
          const topY = padding.top + innerHeight - filledHeight;
          const isHovered = hoveredIndex === index;
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
              {slot.value !== null ? (
                <rect
                  x={x - barWidth / 2}
                  y={topY}
                  width={barWidth}
                  height={Math.max(filledHeight, 2)}
                  rx={barWidth / 2}
                  className="trend-bar-fill trend-bar-fill-steps"
                  opacity={isHovered ? 0.96 : 0.86}
                />
              ) : null}
              <rect x={x - Math.max(18, barWidth / 2)} y={padding.top} width={Math.max(36, barWidth)} height={innerHeight} fill="transparent" />
              <text x={x} y={height - 16} textAnchor="middle" className="chart-tick">
                {slot.label}
              </text>
            </g>
          );
        })}
      </svg>
    </section>
  );
}
