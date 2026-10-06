"use client";

import { useCallback, useEffect, useState } from "react";
import { Download, Trash2 } from "lucide-react";
import { api, type TestSummary } from "@/lib/api";
import { fmtDateTime, fmtInt, fmtMs, fmtNum } from "@/lib/format";
import { MetricTile } from "@/components/MetricTile";
import { StatusBadge } from "@/components/StatusBadge";

export default function HistoryPage() {
  const [rows, setRows] = useState<TestSummary[]>([]);
  const [selected, setSelected] = useState<TestSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.history();
      setRows(data);
      setSelected((prev) =>
        prev ? (data.find((r) => r.id === prev.id) ?? null) : null,
      );
    } catch (e: any) {
      setError(String(e.message ?? e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function remove(id: number) {
    await api.deleteHistory(id);
    if (selected?.id === id) setSelected(null);
    load();
  }

  async function clearAll() {
    if (!confirm("Delete ALL local test history? This cannot be undone.")) return;
    await api.clearHistory();
    setSelected(null);
    load();
  }

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Test History</h1>
          <p className="text-sm text-slate-500">
            Previous load tests stored locally in SQLite.
          </p>
        </div>
        {rows.length > 0 && (
          <div className="flex gap-2">
            <a className="btn-ghost" href={api.exportUrl("csv")}>
              <Download size={16} /> CSV
            </a>
            <a className="btn-ghost" href={api.exportUrl("json")}>
              <Download size={16} /> JSON
            </a>
            <button className="btn-ghost text-red-600" onClick={clearAll}>
              <Trash2 size={16} /> Clear all
            </button>
          </div>
        )}
      </header>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {loading ? (
        <p className="text-sm text-slate-400">Loading…</p>
      ) : rows.length === 0 ? (
        <div className="card p-8 text-center text-sm text-slate-500">
          No tests have been run yet. Start one from the Dashboard.
        </div>
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3">ID</th>
                <th className="px-4 py-3">Target</th>
                <th className="px-4 py-3">Started</th>
                <th className="px-4 py-3">Users</th>
                <th className="px-4 py-3">Reqs</th>
                <th className="px-4 py-3">RPS</th>
                <th className="px-4 py-3">P95</th>
                <th className="px-4 py-3">Err%</th>
                <th className="px-4 py-3">Result</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((r) => (
                <tr
                  key={r.id}
                  className="cursor-pointer hover:bg-slate-50"
                  onClick={() => setSelected(r)}
                >
                  <td className="px-4 py-3 font-medium">{r.id}</td>
                  <td className="max-w-[200px] truncate px-4 py-3">{r.targetUrl}</td>
                  <td className="px-4 py-3 text-slate-500">{fmtDateTime(r.startTime)}</td>
                  <td className="px-4 py-3">{fmtInt(r.maxUsers)}</td>
                  <td className="px-4 py-3">{fmtInt(r.totalRequests)}</td>
                  <td className="px-4 py-3">{fmtNum(r.requestsPerSecond)}</td>
                  <td className="px-4 py-3">{fmtMs(r.p95Ms)}</td>
                  <td className="px-4 py-3">{fmtNum(r.errorRatePct, 2)}</td>
                  <td className="px-4 py-3">
                    <StatusBadge result={r.result} />
                  </td>
                  <td className="px-4 py-3">
                    <button
                      className="text-slate-400 hover:text-red-600"
                      onClick={(e) => {
                        e.stopPropagation();
                        remove(r.id);
                      }}
                      aria-label="Delete"
                    >
                      <Trash2 size={16} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selected && (
        <section className="card p-6">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">Test #{selected.id}</h2>
            <StatusBadge result={selected.result} />
          </div>
          <p className="mt-1 break-all text-sm text-slate-500">{selected.targetUrl}</p>
          <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
            <MetricTile label="Duration" value={`${fmtNum(selected.durationSeconds)} s`} />
            <MetricTile label="Peak users" value={fmtInt(selected.maxUsers)} />
            <MetricTile label="Total requests" value={fmtInt(selected.totalRequests)} />
            <MetricTile label="Requests/sec" value={fmtNum(selected.requestsPerSecond)} />
            <MetricTile label="P50" value={fmtMs(selected.p50Ms)} />
            <MetricTile label="P95" value={fmtMs(selected.p95Ms)} />
            <MetricTile label="P99" value={fmtMs(selected.p99Ms)} />
            <MetricTile label="Error rate" value={`${fmtNum(selected.errorRatePct, 2)}%`} />
          </div>
          <p className="mt-4 text-sm text-slate-500">Stop reason: {selected.stopReason}</p>
          <div className="mt-4 flex gap-2">
            <a className="btn-ghost" href={api.exportUrl("csv", selected.id)}>
              <Download size={16} /> CSV
            </a>
            <a className="btn-ghost" href={api.exportUrl("json", selected.id)}>
              <Download size={16} /> JSON
            </a>
            <button className="btn-ghost text-red-600" onClick={() => remove(selected.id)}>
              <Trash2 size={16} /> Delete record
            </button>
          </div>
        </section>
      )}
    </div>
  );
}
