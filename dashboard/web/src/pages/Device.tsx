import { useEffect, useState } from "react";
import { dashboardApi } from "../api/client";
import type { DataQualityResponse, DeviceStatusResponse } from "../api/types";
import { DataQualityBadge } from "../components/DataQualityBadge";

export function Device({ device }: { device: string }) {
  const [status, setStatus] = useState<DeviceStatusResponse | null>(null);
  const [quality, setQuality] = useState<DataQualityResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([dashboardApi.deviceStatus(device), dashboardApi.dataQuality(device)]).then(([statusPayload, qualityPayload]) => {
      if (!cancelled) {
        setStatus(statusPayload);
        setQuality(qualityPayload);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [device]);

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
