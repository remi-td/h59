import { useMemo, useState } from "react";
import type { MetricPoint } from "../api/types";

function formatPoint(point: MetricPoint, unit?: string): string {
  const stamp = new Date(point.timestamp).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  const value = Number(point.value ?? 0);
  return `${stamp} · ${value.toFixed(0)}${unit ? ` ${unit}` : ""}`;
}

export function DailyBars({
  points,
  title,
  color = "var(--accent-2)",
  unit,
  yAxisLabel = "Value",
  xAxisLabel = "Day",
  onPointSelect,
  selectedTimestamp,
}: {
  points: MetricPoint[];
  title?: string;
  color?: string;
  unit?: string | null;
  yAxisLabel?: string;
  xAxisLabel?: string;
  onPointSelect?: (point: MetricPoint) => void;
  selectedTimestamp?: string | null;
}) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const values = useMemo(() => points.map((point) => Number(point.value ?? 0)), [points]);
  const max = Math.max(...values, 1);
  const hovered = hoveredIndex !== null ? points[hoveredIndex] : points[points.length - 1];

  if (!points.length) {
    return <div className="panel-empty">No bar data</div>;
  }

  return (
    <section className="chart-panel">
      {title ? (
        <header className="chart-panel-header">
          <h3>{title}</h3>
          <p className="chart-hover-readout">{hovered ? formatPoint(hovered, unit || undefined) : "No data"}</p>
        </header>
      ) : null}
      <div className="bar-chart-meta">
        <span className="chart-axis-label">{yAxisLabel}</span>
        <span className="chart-axis-label">{xAxisLabel}</span>
      </div>
      <div className="bar-chart">
        {points.map((point, index) => {
          const isSelected = selectedTimestamp === point.timestamp;
          return (
            <button
              type="button"
              key={point.timestamp}
              className={`bar-column-button${isSelected ? " is-selected" : ""}`}
              onMouseEnter={() => setHoveredIndex(index)}
              onFocus={() => setHoveredIndex(index)}
              onMouseLeave={() => setHoveredIndex(null)}
              onBlur={() => setHoveredIndex(null)}
              onClick={() => onPointSelect?.(point)}
              title={formatPoint(point, unit || undefined)}
            >
              <div className="bar-column">
                <div className="bar-track">
                  <div className="bar-fill" style={{ height: `${(Number(point.value ?? 0) / max) * 100}%`, background: color }} />
                </div>
                <span>{new Date(point.timestamp).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</span>
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
}
