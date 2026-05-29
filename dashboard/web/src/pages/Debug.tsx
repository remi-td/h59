import { useEffect, useState } from "react";
import { dashboardApi } from "../api/client";
import type { DebugResponse } from "../api/types";

export function Debug({ device }: { device: string }) {
  const [data, setData] = useState<DebugResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    dashboardApi.debug(device).then((payload) => {
      if (!cancelled) {
        setData(payload);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [device]);

  return (
    <div className="stack-layout">
      <section className="table-panel">
        <header><h3>Decoded Table Counts</h3></header>
        <div className="table-scroll">
          <table>
            <thead>
              <tr><th>Table</th><th>Rows</th></tr>
            </thead>
            <tbody>
              {Object.entries(data?.table_counts || {}).map(([table, count]) => (
                <tr key={table}>
                  <td>{table}</td>
                  <td>{count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="table-panel">
        <header><h3>Recent Syncs</h3></header>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Sync</th>
                <th>Started</th>
                <th>Finished</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {(data?.recent_syncs || []).map((sync) => (
                <tr key={String(sync.sync_id)}>
                  <td>{String(sync.sync_id)}</td>
                  <td>{String(sync.started_at)}</td>
                  <td>{String(sync.finished_at)}</td>
                  <td>{String(sync.source)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
