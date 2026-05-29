import { useDeviceData } from "../api/hooks";
import { DataQualityBadge } from "../components/DataQualityBadge";

export function Device({ device }: { device: string }) {
  const { data, error, loading } = useDeviceData(device);
  const status = data?.status ?? null;
  const quality = data?.quality ?? null;

  if (error) {
    return <div className="panel-error">{error}</div>;
  }
  if (loading) {
    return <div className="panel-loading">Loading device status…</div>;
  }

  return (
    <div className="stack-layout">
      <section className="metric-card hero-card">
        <div className="metric-card-top">
          <div>
            <p className="eyebrow">Device Status</p>
            <h2>{status?.device.nickname || status?.device.name || "Preferred Device"}</h2>
          </div>
          <DataQualityBadge status={quality?.status || "empty"} />
        </div>
        <p className="metric-subtitle">Battery {status?.device.battery_percent ?? "n/a"}% {status?.battery_charging ? "· charging" : ""}</p>
        <p className="metric-subtitle">Last sync {quality?.last_successful_sync || "n/a"}</p>
        <p className="metric-subtitle">Latest sample {status?.last_sample_timestamp || "n/a"}</p>
      </section>

      <section className="table-panel">
        <header><h3>Latest Sample Timestamps</h3></header>
        <div className="table-scroll">
          <table>
            <thead>
              <tr><th>Metric</th><th>Timestamp</th></tr>
            </thead>
            <tbody>
              {Object.entries(status?.latest_samples || {}).map(([metric, timestamp]) => (
                <tr key={metric}>
                  <td>{metric}</td>
                  <td>{timestamp || "n/a"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="table-panel">
        <header><h3>Today’s Sample Counts</h3></header>
        <div className="table-scroll">
          <table>
            <thead>
              <tr><th>Metric</th><th>Count</th></tr>
            </thead>
            <tbody>
              {Object.entries(quality?.sample_counts_today || {}).map(([metric, count]) => (
                <tr key={metric}>
                  <td>{metric}</td>
                  <td>{count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
