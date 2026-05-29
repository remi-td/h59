import { useMemo } from "react";
import type { SleepStageSegment } from "../api/types";
import { formatTime } from "../lib/format";

const STAGE_COLORS: Record<string, string> = {
  deep: "var(--accent-1)",
  light: "var(--accent-3)",
  rem: "var(--accent-2)",
  awake: "var(--accent-4)",
  unknown: "var(--ink-soft)",
};

function stageColor(stage: string): string {
  return STAGE_COLORS[stage] || STAGE_COLORS.unknown;
}

function stageLabel(stage: string): string {
  return stage.toUpperCase();
}

export function SleepTimeline({
  stages,
  title = "Sleep Timeline",
  subtitle,
}: {
  stages: SleepStageSegment[];
  title?: string;
  subtitle?: string | null;
}) {
  const legendEntries = useMemo(() => {
    const totals = new Map<string, number>();
    stages.forEach((stage) => {
      totals.set(stage.stage, (totals.get(stage.stage) || 0) + stage.minutes);
    });
    return Array.from(totals.entries()).map(([stage, minutes]) => ({ stage, minutes }));
  }, [stages]);

  if (!stages.length) {
    return <div className="panel-empty">No sleep stage segments</div>;
  }
  const total = stages.reduce((sum, stage) => sum + stage.minutes, 0) || 1;
  return (
    <section className="chart-panel">
      <header className="chart-panel-header">
        <div>
          <h3>{title}</h3>
          {subtitle ? <p className="chart-hover-readout">{subtitle}</p> : null}
        </div>
      </header>
      <div className="sleep-timeline">
        {stages.map((stage, index) => (
          <div
            key={`${stage.stage}-${index}`}
            className="sleep-segment"
            style={{
              width: `${(stage.minutes / total) * 100}%`,
              background: stageColor(stage.stage),
            }}
            title={`${stageLabel(stage.stage)} · ${stage.minutes} min${stage.start_timestamp ? ` · ${formatTime(stage.start_timestamp)}` : ""}${stage.end_timestamp ? ` -> ${formatTime(stage.end_timestamp)}` : ""}`}
          />
        ))}
      </div>
      <div className="sleep-legend">
        {legendEntries.map((entry) => (
          <span key={entry.stage} className="sleep-legend-item">
            <span className="sleep-legend-swatch" style={{ background: stageColor(entry.stage) }} />
            <span>{stageLabel(entry.stage)} · {entry.minutes} min</span>
          </span>
        ))}
      </div>
    </section>
  );
}
