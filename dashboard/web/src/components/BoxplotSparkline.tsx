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

function formatBoxStats(point: BoxPoint, unit?: string | null): string {
  const suffix = unit ? ` ${unit}` : "";
  if (point.median === null) {
    return `${formatShortDate(point.timestamp)} · n/a`;
  }
  return `${formatShortDate(point.timestamp)} · min ${point.min?.toFixed(0) ?? "n/a"}${suffix} · q1 ${point.q1?.toFixed(0) ?? "n/a"}${suffix} · med ${point.median.toFixed(0)}${suffix} · q3 ${point.q3?.toFixed(0) ?? "n/a"}${suffix} · max ${point.max?.toFixed(0) ?? "n/a"}${suffix}`;
}

export function BoxplotSparkline({
  points,
  unit,
  color = "var(--accent-4)",
}: {
  points: MetricPoint[];
  unit?: string | null;
  color?: string;
}) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const chartPoints = useMemo(() => points.map(asBoxPoint), [points]);
  const validPoints = chartPoints.filter((point) => point.median !== null);

  if (validPoints.length < 1) {
    return <div className="sparkline-empty">No trend</div>;
  }

  const width = 140;
  const height = 54;
  const top = 5;
  const bottom = height - 8;
  const min = Math.min(...validPoints.map((point) => point.min ?? point.median ?? 0));
  const max = Math.max(...validPoints.map((point) => point.max ?? point.median ?? 0));
  const span = max - min || 1;
  const activeIndex = hoveredIndex ?? (() => {
    for (let index = chartPoints.length - 1; index >= 0; index -= 1) {
      if (chartPoints[index].median !== null) {
        return index;
      }
    }
    return 0;
  })();
  const active = chartPoints[Math.max(activeIndex, 0)];

  const yFor = (value: number) => top + (1 - (value - min) / span) * (bottom - top);

  return (
    <div className="sparkline-wrap">
      <p className="sparkline-readout">{formatBoxStats(active, unit)}</p>
      <svg className="sparkline sparkline-boxplot" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
        {chartPoints.map((point, index) => {
          const x = (index / Math.max(chartPoints.length - 1, 1)) * width;
          if (point.median === null || point.min === null || point.q1 === null || point.q3 === null || point.max === null) {
            return (
              <circle
                key={`${point.timestamp}-${index}`}
                cx={x}
                cy={bottom}
                r={1.5}
                fill="rgba(104,117,106,0.4)"
                onMouseEnter={() => setHoveredIndex(index)}
                onFocus={() => setHoveredIndex(index)}
                onMouseLeave={() => setHoveredIndex(null)}
                onBlur={() => setHoveredIndex(null)}
              />
            );
          }
          const boxTop = yFor(point.q3);
          const boxBottom = yFor(point.q1);
          const medianY = yFor(point.median);
          const minY = yFor(point.min);
          const maxY = yFor(point.max);
          const boxWidth = 12;
          return (
            <g
              key={`${point.timestamp}-${index}`}
              onMouseEnter={() => setHoveredIndex(index)}
              onFocus={() => setHoveredIndex(index)}
              onMouseLeave={() => setHoveredIndex(null)}
              onBlur={() => setHoveredIndex(null)}
            >
              <title>{formatBoxStats(point, unit)}</title>
              <line x1={x} y1={maxY} x2={x} y2={minY} className="boxplot-whisker" />
              <line x1={x - 4} y1={maxY} x2={x + 4} y2={maxY} className="boxplot-cap" />
              <line x1={x - 4} y1={minY} x2={x + 4} y2={minY} className="boxplot-cap" />
              <rect x={x - boxWidth / 2} y={boxTop} width={boxWidth} height={Math.max(boxBottom - boxTop, 2)} className="boxplot-box" style={{ fill: color }} opacity={hoveredIndex === index ? 0.9 : 0.7} />
              <line x1={x - boxWidth / 2} y1={medianY} x2={x + boxWidth / 2} y2={medianY} className="boxplot-median" />
              <rect x={x - 8} y={top} width={16} height={bottom - top} fill="transparent" />
            </g>
          );
        })}
      </svg>
    </div>
  );
}
