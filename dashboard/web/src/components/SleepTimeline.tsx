import { useMemo, useState } from "react";
import type { SleepStageSegment } from "../api/types";
import { formatDurationMinutes, formatSleepWindow } from "../lib/format";
import { sleepStageColor } from "../lib/sleep-stage-colors";

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
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  if (!stages.length) {
    return <div className="panel-empty">No sleep stage segments</div>;
  }
  const total = stages.reduce((sum, stage) => sum + stage.minutes, 0) || 1;
  const hoveredStage = hoveredIndex === null ? null : stages[hoveredIndex];
  const readout = hoveredStage
    ? `${stageLabel(hoveredStage.stage)} · ${formatSleepWindow(hoveredStage.start_timestamp, hoveredStage.end_timestamp)} · ${formatDurationMinutes(hoveredStage.minutes)}`
    : subtitle;
  return (
    <section className="chart-panel">
      <header className="chart-panel-header">
        <div>
          <h3>{title}</h3>
          {readout ? <p className="sleep-timeline-readout">{readout}</p> : null}
        </div>
      </header>
      <div className="sleep-timeline">
        {stages.map((stage, index) => (
          <div
            key={`${stage.stage}-${index}`}
            className="sleep-segment"
            style={{
              width: `${(stage.minutes / total) * 100}%`,
              background: sleepStageColor(stage.stage),
            }}
            onMouseEnter={() => setHoveredIndex(index)}
            onMouseLeave={() => setHoveredIndex((current) => (current === index ? null : current))}
          />
        ))}
      </div>
      <div className="sleep-legend">
        {legendEntries.map((entry) => (
          <span key={entry.stage} className="sleep-legend-item">
            <span className="sleep-legend-swatch" style={{ background: sleepStageColor(entry.stage) }} />
            <span>{stageLabel(entry.stage)} · {formatDurationMinutes(entry.minutes)}</span>
          </span>
        ))}
      </div>
    </section>
  );
}
