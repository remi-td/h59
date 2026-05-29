import type { MetricCardData } from "../api/types";
import { BoxplotSparkline } from "./BoxplotSparkline";
import { DataQualityBadge } from "./DataQualityBadge";
import { Sparkline } from "./Sparkline";
import { SleepStagePie } from "./SleepStagePie";
import { TrustBadge } from "./TrustBadge";
import { formatSleepWindow } from "../lib/format";


function formatValue(card: MetricCardData): string {
  if (card.display_value) {
    return card.display_value;
  }
  if (card.value === null || card.value === undefined || card.value === "") {
    return "N/A";
  }
  return card.unit ? `${card.value} ${card.unit}` : String(card.value);
}
function formatSubtitle(card: MetricCardData): string | null {
  if (!card.subtitle) {
    return null;
  }
  if (card.id === "sleep" && card.subtitle.includes(" -> ")) {
    const [start, end] = card.subtitle.split(" -> ", 2);
    return formatSleepWindow(start, end);
  }
  return card.subtitle;
}

export function MetricCard({ card }: { card: MetricCardData }) {
  const subtitle = formatSubtitle(card);
  return (
    <article className="metric-card">
      <div className="metric-card-top">
        <div>
          <p className="eyebrow">{card.title}</p>
          <h3>{formatValue(card)}</h3>
        </div>
        <div className="badge-stack">
          <TrustBadge trustClass={card.trust_class} />
          <DataQualityBadge status={card.status} />
        </div>
      </div>
      {card.summary ? (
        <p className="metric-summary">
          min {card.summary.min ?? "n/a"} · avg {card.summary.avg ?? "n/a"} · max {card.summary.max ?? "n/a"}
        </p>
      ) : null}
      {subtitle ? <p className="metric-subtitle">{subtitle}</p> : null}
      {card.id === "sleep" && card.breakdown.length ? <SleepStagePie items={card.breakdown} /> : null}
      {card.sparkline.length && card.trend_type === "boxplot" ? <BoxplotSparkline points={card.sparkline} unit={card.unit} /> : null}
      {card.sparkline.length && card.trend_type !== "boxplot" && card.trend_type !== "none" ? <Sparkline points={card.sparkline} unit={card.unit} /> : null}
    </article>
  );
}
