import { useMemo, useState } from "react";
import type { MetricPoint } from "../api/types";
import { formatTime } from "../lib/format";

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

function formatMeasurement(point: MetricPoint, unit?: string | null): string {
  const value = metricValue(point);
  if (value === null) {
    return `${formatTime(point.timestamp)} · n/a`;
  }
  return `${formatTime(point.timestamp)} · ${Number.isInteger(value) ? value.toFixed(0) : value.toFixed(1)}${unit ? ` ${unit}` : ""}`;
}

export function Sparkline({
  points,
  unit,
  color = "var(--accent-2)",
}: {
  points: MetricPoint[];
  unit?: string | null;
  color?: string;
}) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const width = 140;
  const height = 44;
  const valuePoints = useMemo(
    () => points.map((point) => ({ point, value: metricValue(point) })),
    [points],
  );
  const plottedValues = valuePoints.filter((entry): entry is { point: MetricPoint; value: number } => entry.value !== null);

  if (plottedValues.length < 2) {
    return <div className="sparkline-empty">No trend</div>;
  }

  const min = Math.min(...plottedValues.map((entry) => entry.value));
  const max = Math.max(...plottedValues.map((entry) => entry.value));
  const span = max - min || 1;
  const chartPoints = valuePoints.map((entry, index) => {
    const x = (index / Math.max(valuePoints.length - 1, 1)) * width;
    const y = entry.value === null ? null : height - ((entry.value - min) / span) * (height - 10) - 5;
    return { ...entry, x, y };
  });
  const fallbackIndex = (() => {
    for (let index = chartPoints.length - 1; index >= 0; index -= 1) {
      if (chartPoints[index].value !== null) {
        return index;
      }
    }
    return 0;
  })();
  const activeIndex = hoveredIndex ?? fallbackIndex;
  const active = chartPoints[Math.max(activeIndex, 0)];

  const segments: string[] = [];
  let currentSegment: string[] = [];
  chartPoints.forEach((entry) => {
    if (entry.y === null) {
      if (currentSegment.length >= 2) {
        segments.push(currentSegment.join(" "));
      }
      currentSegment = [];
      return;
    }
    currentSegment.push(`${currentSegment.length === 0 ? "M" : "L"} ${entry.x},${entry.y}`);
  });
  if (currentSegment.length >= 2) {
    segments.push(currentSegment.join(" "));
  }

  return (
    <div className="sparkline-wrap">
      <p className="sparkline-readout">{formatMeasurement(active.point, unit)}</p>
      <svg className="sparkline" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
        {segments.map((segment, index) => (
          <path key={`segment-${index}`} d={segment} fill="none" stroke={color} strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round" />
        ))}
        {chartPoints.map((entry, index) =>
          entry.y === null ? (
            <circle
              key={`${entry.point.timestamp}-${index}`}
              cx={entry.x}
              cy={height - 4}
              r={6}
              fill="transparent"
              onMouseEnter={() => setHoveredIndex(index)}
              onFocus={() => setHoveredIndex(index)}
              onMouseLeave={() => setHoveredIndex(null)}
              onBlur={() => setHoveredIndex(null)}
            />
          ) : (
            <g key={`${entry.point.timestamp}-${index}`}>
              <circle
                cx={entry.x}
                cy={entry.y}
                r={8}
                fill="transparent"
                onMouseEnter={() => setHoveredIndex(index)}
                onFocus={() => setHoveredIndex(index)}
                onMouseLeave={() => setHoveredIndex(null)}
                onBlur={() => setHoveredIndex(null)}
              >
                <title>{formatMeasurement(entry.point, unit)}</title>
              </circle>
            </g>
          ),
        )}
      </svg>
    </div>
  );
}
