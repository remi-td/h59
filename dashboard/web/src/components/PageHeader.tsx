import type { DeviceSummary } from "../api/types";
import { DataQualityBadge } from "./DataQualityBadge";
import { formatDateTime } from "../lib/format";

export function PageHeader({
  title,
  subtitle,
  reportDate,
  lastSync,
  devices,
  device,
  onDeviceChange,
}: {
  title: string;
  subtitle?: string;
  reportDate?: string | null;
  lastSync?: string | null;
  devices: DeviceSummary[];
  device: string;
  onDeviceChange: (value: string) => void;
}) {
  return (
    <header className="page-header">
      <div className="page-header-copy">
        <p className="eyebrow">H59 Local Dashboard</p>
        <h1>{title}</h1>
        <div className="page-meta-line">
          {subtitle ? <p className="page-subtitle">{subtitle}</p> : null}
          {reportDate ? (
            <p className="page-sync-meta">
              <span className="page-sync-label">Report date</span>
              <span>{reportDate}</span>
            </p>
          ) : null}
          <p className="page-sync-meta">
            <span className="page-sync-label">Last sync</span>
            <span>{lastSync ? formatDateTime(lastSync) : "No sync recorded yet"}</span>
          </p>
        </div>
      </div>
      <div className="page-header-controls">
        <label className="device-selector">
          <span>Device</span>
          <select value={device} onChange={(event) => onDeviceChange(event.target.value)}>
            <option value="preferred">Preferred</option>
            {devices.map((item) => (
              <option key={item.id} value={item.nickname || String(item.id)}>
                {item.nickname || item.name || `device-${item.id}`}
              </option>
            ))}
          </select>
        </label>
        {devices.find((item) => (item.nickname || String(item.id)) === device || (device === "preferred" && item.is_preferred)) ? (
          <DataQualityBadge
            status={(devices.find((item) => (item.nickname || String(item.id)) === device || (device === "preferred" && item.is_preferred))?.data_freshness) || "empty"}
          />
        ) : null}
      </div>
    </header>
  );
}
