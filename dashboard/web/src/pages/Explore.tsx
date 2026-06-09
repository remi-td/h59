import { useEffect, useMemo, useState } from "react";
import { dashboardApi } from "../api/client";
import type { FeatureSeriesResponse, MetricCatalogItem } from "../api/types";

const DEFAULT_METRIC = "sleep.efficiency_pct";

function formatValue(value: number | null | undefined, unit?: string | null): string {
  if (value === null || value === undefined) return "n/a";
  const rendered = Math.abs(value) >= 100 ? value.toFixed(0) : value.toFixed(1);
  return `${rendered}${unit ? ` ${unit}` : ""}`;
}

export function Explore({ device }: { device: string }) {
  const [catalog, setCatalog] = useState<MetricCatalogItem[]>([]);
  const [metric, setMetric] = useState(DEFAULT_METRIC);
  const [payload, setPayload] = useState<FeatureSeriesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    dashboardApi
      .metricCatalog()
      .then((data) => {
        if (!cancelled) {
          setCatalog(data.metrics ?? []);
          if (!data.metrics?.some((item) => item.metric_key === metric) && data.metrics?.length) {
            setMetric(data.metrics[0].metric_key);
          }
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    dashboardApi
      .features(device, [metric], true)
      .then((data) => {
        if (!cancelled) setPayload(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [device, metric]);

  const selected = useMemo(() => catalog.find((item) => item.metric_key === metric), [catalog, metric]);
  const observations = payload?.series?.[0]?.observations ?? [];

  return (
    <div className="stack-layout">
      <section className="chart-panel">
        <div className="chart-panel-header">
          <div>
            <p className="eyebrow">Metric explorer</p>
            <h3>Feature-store catalog</h3>
            <p className="metric-subtitle">Catalog-powered observations with provenance, baselines, quality, and confidence.</p>
          </div>
        </div>
        {error ? <div className="panel-error">{error}</div> : null}
        <label className="device-selector">
          <span>Metric</span>
          <select value={metric} onChange={(event) => setMetric(event.target.value)}>
            {catalog.map((item) => (
              <option key={item.metric_key} value={item.metric_key}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        {selected ? (
          <p className="metric-subtitle">
            {selected.description} · {selected.approximation_level} · {selected.source}
          </p>
        ) : null}
      </section>

      <section className="chart-panel">
        <div className="chart-panel-header">
          <div>
            <p className="eyebrow">Recent observations</p>
            <h3>Daily feature values</h3>
            <p className="metric-subtitle">Missing-data-aware daily rows from /api/features.</p>
          </div>
        </div>
        <div className="page-grid">
          {observations.slice(-14).map((point) => (
            <article key={`${point.metric_key}-${point.feature_date}`} className="metric-card">
              <div className="metric-card-top">
                <div>
                  <p className="metric-label">{point.feature_date}</p>
                  <h3>{formatValue(point.value, point.unit)}</h3>
                </div>
                <span className="data-quality-badge">{point.data_quality_state ?? "unknown"}</span>
              </div>
              <p className="metric-subtitle">
                confidence {Math.round((point.confidence ?? 0) * 100)}% · {point.sample_count ?? 0} samples
              </p>
              {point.baseline ? <p className="metric-subtitle">30d median {formatValue(point.baseline.median, point.unit)}</p> : null}
            </article>
          ))}
          {!observations.length ? <p className="metric-subtitle">No observations available for this metric/device.</p> : null}
        </div>
      </section>
    </div>
  );
}
