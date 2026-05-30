import { useEffect, useMemo, useState } from "react";
import { useSleep } from "../api/hooks";
import type { SleepSessionSummary } from "../api/types";
import { SleepTimeline } from "../components/SleepTimeline";
import { TrendEChart } from "../components/TrendEChart";
import { latestSleepSummary, rollingDaySlots, sleepStageTrendOption } from "../components/trend-options";
import { formatDateTime, formatDurationMinutes, formatSleepWindow } from "../lib/format";

function sessionKey(session: SleepSessionSummary): string {
  return `${session.start_timestamp || "unknown"}-${session.end_timestamp || "unknown"}`;
}

function sameNightKey(session: SleepSessionSummary): string | null {
  const stamp = session.end_timestamp || session.start_timestamp;
  return stamp ? stamp.slice(0, 10) : null;
}

export function Sleep({ device }: { device: string }) {
  const { data, error, loading } = useSleep(device, "14d");
  const [selectedKey, setSelectedKey] = useState<string | null>(null);

  useEffect(() => {
    if (data?.latest_session) {
      setSelectedKey(sessionKey(data.latest_session));
    } else {
      setSelectedKey(null);
    }
  }, [data?.latest_session]);

  const endDate = useMemo(() => {
    const last = data?.sessions[0];
    return (last?.end_timestamp || last?.start_timestamp || null)?.slice(0, 10) ?? null;
  }, [data]);
  const slots = useMemo(() => rollingDaySlots(endDate, 14), [endDate]);
  const option = useMemo(() => sleepStageTrendOption(data?.sessions || [], slots), [data, slots]);

  const selectedSession =
    (data?.sessions || []).find((session) => sessionKey(session) === selectedKey) ||
    data?.latest_session ||
    null;

  const onSleepChartClick = useMemo(
    () => ({
      click: (params: any) => {
        const slot = slots[Number(params?.dataIndex)];
        if (!slot) {
          return;
        }
        const matched = (data?.sessions || []).find((session) => sameNightKey(session) === slot.key);
        if (matched) {
          setSelectedKey(sessionKey(matched));
        }
      },
    }),
    [data, slots],
  );

  if (error) {
    return <div className="panel-error">{error}</div>;
  }
  if (loading) {
    return <div className="panel-loading">Loading sleep history…</div>;
  }

  return (
    <div className="stack-layout">
        <TrendEChart
          title="Sleep Duration by Night"
          note="Rolling 14 nights · stacked by stage"
          summary={latestSleepSummary(data?.sessions || [])}
          option={option}
          emptyMessage="No sleep history"
        onEvents={onSleepChartClick}
      />
      <SleepTimeline
        stages={selectedSession?.stages || []}
        subtitle={
          selectedSession
            ? `${formatSleepWindow(selectedSession.start_timestamp, selectedSession.end_timestamp)} · ${formatDurationMinutes(selectedSession.total_minutes)}`
            : "Select a sleep session to inspect its stage timeline"
        }
      />
      <section className="table-panel">
        <header><h3>Recent Sleep Sessions</h3></header>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Session</th>
                <th>End</th>
                <th>Total</th>
                <th>State</th>
              </tr>
            </thead>
            <tbody>
              {(data?.sessions || []).map((session, index) => {
                const selected = Boolean(selectedSession && sessionKey(selectedSession) === sessionKey(session));
                return (
                  <tr key={`${session.start_timestamp}-${index}`} className={selected ? "is-selected-row" : undefined}>
                    <td>
                      <button
                        type="button"
                        className="table-row-button"
                        aria-pressed={selected}
                        onClick={() => setSelectedKey(sessionKey(session))}
                      >
                        {formatDateTime(session.start_timestamp)}
                      </button>
                    </td>
                    <td>{formatDateTime(session.end_timestamp)}</td>
                    <td>{formatDurationMinutes(session.total_minutes)}</td>
                    <td>{session.state || "n/a"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
