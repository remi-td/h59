import { useCurrentInsight } from "../api/hooks";
import { formatDateTime, formatDurationMinutes } from "../lib/format";

type ScoreTone = "good" | "watch" | "alert" | "neutral";

function scoreTone(score: number, inverse = false): ScoreTone {
  if (inverse) {
    if (score >= 18) return "alert";
    if (score >= 14) return "watch";
    return "good";
  }
  if (score >= 80) return "good";
  if (score >= 60) return "watch";
  return "alert";
}

function sentenceCase(value: string | null | undefined): string {
  if (!value) return "n/a";
  return value.replace(/_/g, " ").replace(/^./, (char) => char.toUpperCase());
}

function ScoreCard({ title, score, band, tone, detail }: { title: string; score: number; band: string; tone: ScoreTone; detail?: string }) {
  const clamped = Math.max(0, Math.min(100, score));
  return (
    <article className={`insight-score-card insight-tone-${tone}`}>
      <div className="insight-score-card-top">
        <div>
          <p className="eyebrow">{title}</p>
          <h3>{score.toFixed(1)}</h3>
        </div>
        <span className="insight-band">{sentenceCase(band)}</span>
      </div>
      <div className="insight-meter" aria-label={`${title} score ${score.toFixed(1)}`}>
        <span style={{ width: `${clamped}%` }} />
      </div>
      {detail ? <p className="metric-subtitle">{detail}</p> : null}
    </article>
  );
}

function SyncBanner({ freshness, warning, latestSync, ageMinutes }: { freshness: string; warning?: string | null; latestSync?: string | null; ageMinutes?: number | null }) {
  const isWarning = freshness === "stale" || freshness === "partial";
  const age = ageMinutes === null || ageMinutes === undefined ? "age unknown" : `${ageMinutes} min old`;
  return (
    <section className={`insight-sync-banner${isWarning ? " is-warning" : ""}`}>
      <div>
        <p className="eyebrow">Band sync context</p>
        <h2>{sentenceCase(freshness)} data</h2>
      </div>
      <div className="insight-sync-copy">
        <p>{warning ?? "Band data is fresh enough for current-state interpretation."}</p>
        <p>Latest band sync: {formatDateTime(latestSync)} · {age}</p>
      </div>
    </section>
  );
}

export function Insights({ device }: { device: string }) {
  const { data, error, loading } = useCurrentInsight(device);

  if (error) {
    return <div className="panel-error">{error}</div>;
  }
  if (loading || !data) {
    return <div className="panel-loading">Loading health insights…</div>;
  }

  return (
    <div className="insights-page stack-layout">
      <section className="insight-hero hero-card">
        <div className="insight-hero-copy">
          <p className="eyebrow">Current physiological readout</p>
          <h2>{sentenceCase(data.state)}</h2>
          <p>{data.recommended_action}</p>
        </div>
        <div className="insight-hero-meta">
          <span className={`insight-confidence insight-confidence-${data.confidence}`}>{data.confidence} confidence</span>
          <span>As of {formatDateTime(data.as_of)}</span>
        </div>
      </section>

      <SyncBanner
        freshness={data.sync_context.data_freshness}
        warning={data.sync_context.warning}
        latestSync={data.sync_context.latest_band_sync}
        ageMinutes={data.sync_context.sync_age_minutes}
      />

      <section className="insight-score-grid">
        <ScoreCard title="Readiness" score={data.readiness.score} band={data.readiness.band} tone={scoreTone(data.readiness.score)} />
        <ScoreCard
          title="Sleep"
          score={data.sleep.score}
          band={data.sleep.duration_minutes ? formatDurationMinutes(data.sleep.duration_minutes) : "unavailable"}
          tone={scoreTone(data.sleep.score)}
          detail={data.sleep.duration_minutes ? `${data.sleep.duration_minutes} minutes of sleep captured` : "No sleep duration available"}
        />
        <ScoreCard title="Strain" score={data.strain.score} band={data.strain.band} tone={scoreTone(data.strain.score, true)} detail="Activity-load based strain estimate" />
      </section>

      <section className="insight-detail-grid">
        <article className="chart-panel">
          <div className="chart-panel-header">
            <div>
              <p className="eyebrow">Why this reading?</p>
              <h3>Key factors</h3>
            </div>
          </div>
          <ul className="insight-list">
            {data.key_factors.map((factor) => (
              <li key={factor}>{factor}</li>
            ))}
          </ul>
        </article>

        <article className="chart-panel">
          <div className="chart-panel-header">
            <div>
              <p className="eyebrow">Safety & use</p>
              <h3>Guardrails</h3>
            </div>
          </div>
          {data.safety_flags.length ? (
            <div className="insight-warning-block">
              <p className="eyebrow">Safety flags</p>
              <ul className="insight-list">
                {data.safety_flags.map((flag) => (
                  <li key={flag}>{flag}</li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="metric-subtitle">No safety flags from the current wearable pattern.</p>
          )}
          <ul className="insight-list insight-guardrails">
            {data.llm_guardrails.map((guardrail) => (
              <li key={guardrail}>{guardrail}</li>
            ))}
          </ul>
        </article>
      </section>
    </div>
  );
}
