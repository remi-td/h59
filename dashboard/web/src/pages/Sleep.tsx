import { useEffect, useState } from "react";
import { dashboardApi } from "../api/client";
import type { MetricPoint, SleepResponse, SleepSessionSummary } from "../api/types";
import { DailyBars } from "../components/DailyBars";
import { SleepTimeline } from "../components/SleepTimeline";
import { formatDateTime, formatSleepWindow } from "../lib/format";

function sessionKey(session: SleepSessionSummary): string {
  return `${session.start_timestamp || "unknown"}-${session.end_timestamp || "unknown"}`;
}

function sameNight(point: MetricPoint, session: SleepSessionSummary): boolean {
  const pointDay = point.timestamp.slice(0, 10);
  return (session.end_timestamp || session.start_timestamp || "").slice(0, 10) === pointDay;
}

export function Sleep({ device }: { device: string }) {
  const [data, setData] = useState<SleepResponse | null>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    dashboardApi.sleep(device, "30d").then((payload) => {
      if (!cancelled) {
        setData(payload);
        setSelectedKey(payload.latest_session ? sessionKey(payload.latest_session) : null);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [device]);

  const selectedSession =
    (data?.sessions || []).find((session) => sessionKey(session) === selectedKey) ||
    data?.latest_session ||
    null;

  return (
    <div className="stack-layout">
      <DailyBars
        points={data?.daily_totals || []}
        title="Sleep Duration by Night"
        color="var(--accent-1)"
        unit="min"
        yAxisLabel="Sleep duration (min)"
        xAxisLabel="Night"
        selectedTimestamp={(data?.daily_totals || []).find((point) => selectedSession && sameNight(point, selectedSession))?.timestamp || null}
        onPointSelect={(point) => {
          const matched = (data?.sessions || []).find((session) => sameNight(point, session));
          if (matched) {
            setSelectedKey(sessionKey(matched));
          }
        }}
      />
      <SleepTimeline
        stages={selectedSession?.stages || []}
        subtitle={
          selectedSession
            ? `${formatSleepWindow(selectedSession.start_timestamp, selectedSession.end_timestamp)} · ${selectedSession.total_minutes ?? "n/a"} min`
            : "Select a sleep session to inspect its stage timeline"
        }
      />
      <section className="table-panel">
        <header><h3>Recent Sleep Sessions</h3></header>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Start</th>
                <th>End</th>
                <th>Total</th>
                <th>State</th>
              </tr>
            </thead>
            <tbody>
              {(data?.sessions || []).map((session, index) => (
                <tr
                  key={`${session.start_timestamp}-${index}`}
                  className={selectedSession && sessionKey(selectedSession) === sessionKey(session) ? "is-selected-row" : undefined}
                  onClick={() => setSelectedKey(sessionKey(session))}
                >
                  <td>{formatDateTime(session.start_timestamp)}</td>
                  <td>{formatDateTime(session.end_timestamp)}</td>
                  <td>{session.total_minutes ?? "n/a"} min</td>
                  <td>{session.state || "n/a"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
