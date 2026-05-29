import { useState } from "react";
import type { MetricBreakdownItem } from "../api/types";

const STAGE_COLORS: Record<string, string> = {
  deep: "var(--accent-1)",
  light: "var(--accent-3)",
  rem: "var(--accent-2)",
  awake: "var(--accent-4)",
  unknown: "var(--ink-soft)",
};

function colorFor(label: string): string {
  return STAGE_COLORS[label] || STAGE_COLORS.unknown;
}

function polarToCartesian(cx: number, cy: number, radius: number, angleDeg: number) {
  const angleRad = ((angleDeg - 90) * Math.PI) / 180;
  return {
    x: cx + radius * Math.cos(angleRad),
    y: cy + radius * Math.sin(angleRad),
  };
}

function arcPath(cx: number, cy: number, radius: number, startAngle: number, endAngle: number): string {
  const start = polarToCartesian(cx, cy, radius, endAngle);
  const end = polarToCartesian(cx, cy, radius, startAngle);
  const largeArcFlag = endAngle - startAngle > 180 ? 1 : 0;
  return [`M ${cx} ${cy}`, `L ${start.x} ${start.y}`, `A ${radius} ${radius} 0 ${largeArcFlag} 0 ${end.x} ${end.y}`, "Z"].join(" ");
}

function formatSliceLabel(label: string, value: number, percent: number): string {
  return `${label.toUpperCase()} · ${value} min · ${percent}%`;
}

export function SleepStagePie({
  items,
  showLegend = false,
}: {
  items: MetricBreakdownItem[];
  showLegend?: boolean;
}) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  if (!items.length) {
    return null;
  }
  const total = items.reduce((sum, item) => sum + item.value, 0) || 1;
  let cursor = 0;
  const slices = items.map((item) => {
    const portion = (item.value / total) * 360;
    const startAngle = cursor;
    const endAngle = cursor + portion;
    cursor = endAngle;
    return {
      ...item,
      path: arcPath(50, 50, 40, startAngle, endAngle),
      color: colorFor(item.label),
      percent: Math.round((item.value / total) * 100),
    };
  });
  const activeSlice = slices[hoveredIndex ?? 0];

  return (
    <div className="sleep-pie-card">
      <div className="sleep-pie-wrap">
        <svg viewBox="0 0 100 100" className="sleep-pie-chart" aria-label="Sleep stage breakdown">
          {slices.map((slice, index) => (
            <path
              key={slice.label}
              d={slice.path}
              fill={slice.color}
              opacity={hoveredIndex === null || hoveredIndex === index ? 1 : 0.76}
              onMouseEnter={() => setHoveredIndex(index)}
              onFocus={() => setHoveredIndex(index)}
              onMouseLeave={() => setHoveredIndex(null)}
              onBlur={() => setHoveredIndex(null)}
            >
              <title>{formatSliceLabel(slice.label, slice.value, slice.percent)}</title>
            </path>
          ))}
          <circle cx="50" cy="50" r="20" fill="rgba(255, 250, 242, 0.96)" />
        </svg>
        <p className="sleep-pie-readout">{formatSliceLabel(activeSlice.label, activeSlice.value, activeSlice.percent)}</p>
      </div>
      {showLegend ? (
        <div className="sleep-pie-legend">
          {slices.map((slice) => (
            <span key={`${slice.label}-legend`} className="sleep-pie-legend-item">
              <span className="sleep-pie-swatch" style={{ background: slice.color }} />
              <span>{slice.label.toUpperCase()} {slice.value}m</span>
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}
