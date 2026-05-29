import { useMemo, useState } from "react";
import type { MetricPoint } from "../api/types";
import { formatShortDate } from "../lib/format";

type BoxPoint = MetricPoint & {
  min: number | null;
  q1: number | null;
  median: number | null;
  q3: number | null;
  max: number | null;
};

function asBoxPoint(point: MetricPoint): BoxPoint {
  return {
    ...point,
    min: point.min_value !== null && point.min_value !== undefined ? Number(point.min_value) : null,
    q1: point.lower_quartile !== null && point.lower_quartile !== undefined ? Number(point.lower_quartile) : null,
    median: point.median_value !== null && point.median_value !== undefined ? Number(point.median_value) : null,
    q3: point.upper_quartile !== null && point.upper_quartile !== undefined ? Number(point.upper_quartile) : null,
    max: point.max_value !== null && point.max_value !== undefined ? Number(point.max_value) : null,
  };
}

function formatHover(point: BoxPoint, unit?: string | null): string {
  const suffix = unit ? ` ${unit}` : "";
  if (point.median === null) {
    return `${formatShortDate(point.timestamp)} · n/a`;
  }
  return `${formatShortDate(point.timestamp)} · min ${point.min?.toFixed(0) ?? "n/a"}${suffix} · q1 ${point.q1?.toFixed(0) ?? "n/a"}${suffix} · med ${point.median.toFixed(0)}${suffix} · q3 ${point.q3?.toFixed(0) ?? "n/a"}${suffix} · max ${point.max?.toFixed(0) ?? "n/a"}${suffix}`;
}

function formatTick(value: number): string {
  return Number.isInteger(value) ? value.toFixed(0) : value.toFixed(1);
}

function buildSevenDaySlots(points: BoxPoint[], endDate?: string | null): BoxPoint[] {
  const anchor = endDate ? new Date(`${endDate}T00:00:00Z`) : new Date(Math.max(...points.map((point) => new Date(point.timestamp).getTime())));
  if (Number.isNaN(anchor.getTime())) {
    return [];
  }
  const byDay = new Map<string, BoxPoint>();
  for (const point of points) {
    byDay.set(point.timestamp.slice(0, 10), point);
  }
  return Array.from({ length: 7 }, (_, index) => {
    const date = new Date(anchor);
    date.setUTCDate(anchor.getUTCDate() - (6 - index));
    const key = date.toISOString().slice(0, 10);
    return (
      byDay.get(key) ?? {
        timestamp: `${key}T00:00:00+00:00`,
        value: null,
        min: null,
        q1: null,
        median: null,
        q3: null,
        max: null,
      }
    );
  });
}

export function BoxplotTrendChart({
  points,
  title,
  unit,
  endDate,
}: {
  points: MetricPoint[];
  title: string;
  unit?: string | null;
  endDate?: string | null;
}) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const chartPoints = useMemo(() => buildSevenDaySlots(points.map(asBoxPoint), endDate), [points, endDate]);
  const validPoints = chartPoints.filter(
    (point) => point.median !== null && point.min !== null && point.q1 !== null && point.q3 !== null && point.max !== null,
  );

  if (!validPoints.length) {
    return <div className="panel-empty">No heart-rate distribution data</div>;
  }

  const width = 760;
  const height = 260;
  const padding = { top: 18, right: 18, bottom: 52, left: 64 };
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;
  const minimum = Math.min(...validPoints.map((point) => point.min ?? point.median ?? 0));
  const maximum = Math.max(...validPoints.map((point) => point.max ?? point.median ?? 0));
  const span = maximum - minimum || 1;
  const yTicks = Array.from({ length: 4 }, (_, index) => minimum + (span * index) / 3);
  const activeIndex =
    hoveredIndex ??
    (() => {
      for (let index = chartPoints.length - 1; index >= 0; index -= 1) {
        if (chartPoints[index].median !== null) {
          return index;
        }
      }
      return 0;
    })();
  const activePoint = chartPoints[Math.max(activeIndex, 0)];
  const yFor = (value: number) => padding.top + innerHeight - ((value - minimum) / span) * innerHeight;
  const slotWidth = innerWidth / Math.max(chartPoints.length, 1);

  return (
    <section className="chart-panel trend-panel">
      <header className="chart-panel-header">
        <div>
          <h3>{title}</h3>
          <p className="trend-panel-note">Rolling 7 days · min, Q1, median, Q3, max</p>
        </div>
        <div>
          <p className="chart-hover-readout">{formatHover(activePoint, unit)}</p>
        </div>
      </header>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="timeseries-chart boxplot-trend-chart"
        role="img"
        aria-label={title}
      >
        <line
          x1={padding.left}
          y1={padding.top + innerHeight}
          x2={width - padding.right}
          y2={padding.top + innerHeight}
          className="chart-axis"
        />
        <line x1={padding.left} y1={padding.top} x2={padding.left} y2={padding.top + innerHeight} className="chart-axis" />
        {yTicks.map((tick) => {
          const y = yFor(tick);
          return (
            <g key={`y-${tick.toFixed(4)}`}>
              <line x1={padding.left} y1={y} x2={width - padding.right} y2={y} className="chart-gridline" />
              <text x={padding.left - 10} y={y + 4} textAnchor="end" className="chart-tick">
                {formatTick(tick)}
              </text>
            </g>
          );
        })}
        <text
          x={24}
          y={padding.top + innerHeight / 2}
          textAnchor="middle"
          className="chart-axis-label"
          transform={`rotate(-90 24 ${padding.top + innerHeight / 2})`}
        >
          Heart rate distribution (bpm)
        </text>
        <text x={padding.left + innerWidth / 2} y={height - 2} textAnchor="middle" className="chart-axis-label">
          Day
        </text>
        {chartPoints.map((point, index) => {
          const x = padding.left + slotWidth * index + slotWidth / 2;
          if (
            point.median === null ||
            point.min === null ||
            point.q1 === null ||
            point.q3 === null ||
            point.max === null
          ) {
            return (
              <g key={`${point.timestamp}-${index}`}>
                <text x={x} y={height - 18} textAnchor="middle" className="chart-tick">
                  {formatShortDate(point.timestamp)}
                </text>
              </g>
            );
          }
          const boxTop = yFor(point.q3);
          const boxBottom = yFor(point.q1);
          const medianY = yFor(point.median);
          const minY = yFor(point.min);
          const maxY = yFor(point.max);
          const boxWidth = Math.max(24, Math.min(52, slotWidth * 0.58));
          const capWidth = Math.max(8, boxWidth * 0.65);
          const isHovered = hoveredIndex === index;

          return (
            <g
              key={`${point.timestamp}-${index}`}
              onMouseEnter={() => setHoveredIndex(index)}
              onFocus={() => setHoveredIndex(index)}
              onMouseLeave={() => setHoveredIndex(null)}
              onBlur={() => setHoveredIndex(null)}
            >
              <title>{formatHover(point, unit)}</title>
              <line x1={x} y1={maxY} x2={x} y2={minY} className="boxplot-whisker" />
              <line x1={x - capWidth / 2} y1={maxY} x2={x + capWidth / 2} y2={maxY} className="boxplot-cap" />
              <line x1={x - capWidth / 2} y1={minY} x2={x + capWidth / 2} y2={minY} className="boxplot-cap" />
              <rect
                x={x - boxWidth / 2}
                y={boxTop}
                width={boxWidth}
                height={Math.max(boxBottom - boxTop, 2)}
                className="boxplot-box"
                style={{ fill: "var(--accent-4)" }}
                opacity={isHovered ? 0.95 : 0.76}
                rx={4}
              />
              <line x1={x - boxWidth / 2} y1={medianY} x2={x + boxWidth / 2} y2={medianY} className="boxplot-median" />
              <rect
                x={x - Math.max(18, boxWidth / 2)}
                y={padding.top}
                width={Math.max(36, boxWidth)}
                height={innerHeight}
                fill="transparent"
              />
              <text x={x} y={height - 18} textAnchor="middle" className="chart-tick">
                {formatShortDate(point.timestamp)}
              </text>
            </g>
          );
        })}
      </svg>
    </section>
  );
}
