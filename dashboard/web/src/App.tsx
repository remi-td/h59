import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import { useEffect, useState } from "react";
import { dashboardApi } from "./api/client";
import type { DeviceSummary, HealthResponse } from "./api/types";
import { PageHeader } from "./components/PageHeader";
import { Today } from "./pages/Today";
import { Trends } from "./pages/Trends";
import { Sleep } from "./pages/Sleep";
import { Heart } from "./pages/Heart";
import { Oxygen } from "./pages/Oxygen";
import { Activity } from "./pages/Activity";
import { Device } from "./pages/Device";
import { Debug } from "./pages/Debug";

const NAV_ITEMS = [
  ["Today", "/"],
  ["Trends", "/trends"],
  ["Sleep", "/sleep"],
  ["Heart", "/heart"],
  ["Oxygen", "/oxygen"],
  ["Activity", "/activity"],
  ["Device", "/device"],
  ["Debug", "/debug"],
] as const;

export default function App() {
  const location = useLocation();
  const [devices, setDevices] = useState<DeviceSummary[]>([]);
  const [device, setDevice] = useState("preferred");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reportDate, setReportDate] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([dashboardApi.devices(), dashboardApi.health()])
      .then(([deviceList, healthPayload]) => {
        if (!cancelled) {
          setDevices(deviceList);
          setHealth(healthPayload);
          const preferred = deviceList.find((item) => item.is_preferred);
          if (preferred?.nickname) {
            setDevice(preferred.nickname);
          }
        }
      })
      .catch((reason: Error) => {
        if (!cancelled) {
          setError(reason.message);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const selectedDevice =
    devices.find((item) => (device === "preferred" && item.is_preferred) || item.nickname === device || String(item.id) === device || item.address === device) ?? null;

  useEffect(() => {
    if (location.pathname !== "/") {
      setReportDate(null);
    }
  }, [location.pathname]);

  return (
    <div className="app-shell">
      <aside className="app-nav">
        <div className="brand-block">
          <p className="brand-mark">H59</p>
          <p className="brand-copy">Local-first health dashboard</p>
        </div>
        <nav>
          {NAV_ITEMS.map(([label, path]) => (
            <NavLink key={path} to={path} end={path === "/"} className={({ isActive }) => `nav-link${isActive ? " is-active" : ""}`}>
              {label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <main className="app-main">
        <PageHeader
          title="Daily Health Review"
          subtitle={health ? `${health.device_count} registered device${health.device_count === 1 ? "" : "s"} · ${health.db_path}` : "Connecting to local API"}
          reportDate={reportDate}
          lastSync={selectedDevice?.last_sync ?? null}
          devices={devices}
          device={device}
          onDeviceChange={setDevice}
        />
        {error ? <div className="panel-error">{error}</div> : null}
        <Routes>
          <Route path="/" element={<Today device={device} onReportDateChange={setReportDate} />} />
          <Route path="/trends" element={<Trends device={device} />} />
          <Route path="/sleep" element={<Sleep device={device} />} />
          <Route path="/heart" element={<Heart device={device} />} />
          <Route path="/oxygen" element={<Oxygen device={device} />} />
          <Route path="/activity" element={<Activity device={device} />} />
          <Route path="/device" element={<Device device={device} />} />
          <Route path="/debug" element={<Debug device={device} />} />
        </Routes>
      </main>
    </div>
  );
}
