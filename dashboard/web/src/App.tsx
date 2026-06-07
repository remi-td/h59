import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import { Suspense, lazy, useEffect, useState } from "react";
import type { DeviceSummary } from "./api/types";
import { useBootstrapData } from "./api/hooks";
import { PageHeader } from "./components/PageHeader";

const Today = lazy(() => import("./pages/Today").then((module) => ({ default: module.Today })));
const Insights = lazy(() => import("./pages/Insights").then((module) => ({ default: module.Insights })));
const Trends = lazy(() => import("./pages/Trends").then((module) => ({ default: module.Trends })));
const Sleep = lazy(() => import("./pages/Sleep").then((module) => ({ default: module.Sleep })));
const Heart = lazy(() => import("./pages/Heart").then((module) => ({ default: module.Heart })));
const Oxygen = lazy(() => import("./pages/Oxygen").then((module) => ({ default: module.Oxygen })));
const Activity = lazy(() => import("./pages/Activity").then((module) => ({ default: module.Activity })));
const Device = lazy(() => import("./pages/Device").then((module) => ({ default: module.Device })));
const Debug = lazy(() => import("./pages/Debug").then((module) => ({ default: module.Debug })));

const NAV_ITEMS = [
  ["Insights", "/"],
  ["Today", "/today"],
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
  const [device, setDevice] = useState("preferred");
  const [reportDate, setReportDate] = useState<string | null>(null);
  const { data, error } = useBootstrapData();
  const devices = data?.devices ?? [];
  const health = data?.health ?? null;

  useEffect(() => {
    const preferred = devices.find((item) => item.is_preferred);
    if (preferred?.nickname) {
      setDevice((current) => (current === "preferred" ? preferred.nickname || current : current));
    }
  }, [devices]);

  const selectedDevice =
    devices.find((item) => (device === "preferred" && item.is_preferred) || item.nickname === device || String(item.id) === device || item.address === device) ?? null;

  const isInsightsPage = location.pathname === "/";

  useEffect(() => {
    if (location.pathname !== "/today") {
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
          title={isInsightsPage ? "Health Insights" : "Daily Health Review"}
          subtitle={health ? `${health.device_count} registered device${health.device_count === 1 ? "" : "s"} · ${health.db_path}` : "Connecting to local API"}
          reportDate={reportDate}
          lastSync={selectedDevice?.last_sync ?? null}
          timeContext={health?.time_context ?? null}
          devices={devices}
          device={device}
          onDeviceChange={setDevice}
        />
        {error ? <div className="panel-error">{error}</div> : null}
        <Suspense fallback={<div className="panel-loading">Loading dashboard page…</div>}>
          <Routes>
            <Route path="/" element={<Insights device={device} />} />
            <Route path="/today" element={<Today device={device} onReportDateChange={setReportDate} />} />
            <Route path="/trends" element={<Trends device={device} />} />
            <Route path="/sleep" element={<Sleep device={device} />} />
            <Route path="/heart" element={<Heart device={device} />} />
            <Route path="/oxygen" element={<Oxygen device={device} />} />
            <Route path="/activity" element={<Activity device={device} />} />
            <Route path="/device" element={<Device device={device} />} />
            <Route path="/debug" element={<Debug device={device} />} />
          </Routes>
        </Suspense>
      </main>
    </div>
  );
}
