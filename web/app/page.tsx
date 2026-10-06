"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Play, Square, TriangleAlert } from "lucide-react";
import { api, type AppSettings, type CurrentTest, type StartRequest } from "@/lib/api";
import { fmtInt, fmtMs, fmtNum } from "@/lib/format";
import { MetricTile } from "@/components/MetricTile";
import { LiveCharts } from "@/components/LiveCharts";
import { StatusBadge } from "@/components/StatusBadge";

const AUTH_TEXT =
  "I confirm that I own this website or have explicit authorization to perform load testing against it.";

export default function DashboardPage() {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [current, setCurrent] = useState<CurrentTest | null>(null);
  const [error, setError] = useState<string>("");
  const [starting, setStarting] = useState(false);

  // --- form state ---
  const [url, setUrl] = useState("https://example.com");
  const [usersPreset, setUsersPreset] = useState<number | "custom">(100);
  const [customUsers, setCustomUsers] = useState(100);
  const [spawnRate, setSpawnRate] = useState(10);
  const [durationPreset, setDurationPreset] = useState<number | "custom">(60);
  const [customDuration, setCustomDuration] = useState(60);
  const [timeout, setTimeoutS] = useState(10);
  const [method, setMethod] = useState("GET");
  const [pathsText, setPathsText] = useState("/\n/about\n/contact\n/products");
  const [allowPrivate, setAllowPrivate] = useState(false);
  const [authorized, setAuthorized] = useState(false);
  const [errThreshold, setErrThreshold] = useState(5);
  const [p95Threshold, setP95Threshold] = useState(3000);
  const [rlThreshold, setRlThreshold] = useState(2);
  const [seThreshold, setSeThreshold] = useState(2);

  const users = usersPreset === "custom" ? customUsers : usersPreset;
  const duration = durationPreset === "custom" ? customDuration : durationPreset;

  // Load settings once.
  useEffect(() => {
    api
      .getSettings()
      .then((s) => {
        setSettings(s);
        setSpawnRate(s.defaultSpawnRate);
        setTimeoutS(s.defaultTimeoutS);
        setErrThreshold(s.defaultErrorThresholdPct);
        setP95Threshold(s.defaultP95ThresholdMs);
        setAllowPrivate(s.allowPrivateTargets);
      })
      .catch((e) => setError(String(e.message ?? e)));
  }, []);

  // Poll the current test state once per second.
  const poll = useCallback(async () => {
    try {
      const c = await api.current();
      setCurrent(c);
    } catch {
      /* transient network errors are ignored; next tick retries */
    }
  }, []);

  useEffect(() => {
    poll();
    const id = setInterval(poll, 1000);
    return () => clearInterval(id);
  }, [poll]);

  const running = Boolean(current?.exists && current.running);

  const overSingleMachine =
    settings != null && users > settings.singleMachineRecommendedMax;

  async function handleStart() {
    setError("");
    setStarting(true);
    try {
      const paths = pathsText
        .split("\n")
        .map((p) => p.trim())
        .filter(Boolean);
      const req: StartRequest = {
        target_url: url,
        paths: paths.length ? paths : ["/"],
        method,
        virtual_users: users,
        spawn_rate: spawnRate,
        duration_seconds: duration,
        request_timeout_s: timeout,
        allow_private_targets: allowPrivate,
        authorized,
        max_error_rate_pct: errThreshold,
        max_p95_latency_ms: p95Threshold,
        max_rate_limit_pct: rlThreshold,
        max_server_error_pct: seThreshold,
      };
      await api.startTest(req);
      await poll();
    } catch (e: any) {
      setError(String(e.message ?? e));
    } finally {
      setStarting(false);
    }
  }

  async function handleStop() {
    try {
      await api.stop();
      await poll();
    } catch (e: any) {
      setError(String(e.message ?? e));
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">
          Website Load Testing Dashboard
        </h1>
        <p className="text-sm text-slate-500">
          Authorized performance and stress testing
        </p>
      </header>

      <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
        <TriangleAlert size={18} className="mt-0.5 shrink-0" />
        <p>
          <strong>Only test systems you own or are authorized to test.</strong>{" "}
          This tool measures capacity and automatically stops at configured
          safety thresholds — it is not designed to take a site offline.
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {running ? (
        <RunningView current={current!} onStop={handleStop} />
      ) : (
        <>
          {current?.exists && current.result && (
            <SummaryView current={current} />
          )}

          {/* ---------------- Config form ---------------- */}
          <section className="card p-6">
            <h2 className="mb-4 text-lg font-semibold">Target</h2>
            <label className="label">Target URL</label>
            <input
              className="input"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://example.com"
            />

            <h2 className="mb-1 mt-6 text-lg font-semibold">Test configuration</h2>
            <p className="mb-4 text-sm text-slate-500">
              Virtual users are simulated clients, not browser windows.
            </p>

            <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
              <div>
                <label className="label">Virtual users</label>
                <select
                  className="input"
                  value={String(usersPreset)}
                  onChange={(e) =>
                    setUsersPreset(
                      e.target.value === "custom"
                        ? "custom"
                        : Number(e.target.value),
                    )
                  }
                >
                  {settings?.userPresets.map((p) => (
                    <option key={p} value={p}>
                      {fmtInt(p)}
                    </option>
                  ))}
                  <option value="custom">Custom…</option>
                </select>
                {usersPreset === "custom" && (
                  <input
                    type="number"
                    className="input mt-2"
                    min={1}
                    max={settings?.maxUsersHardCap}
                    value={customUsers}
                    onChange={(e) => setCustomUsers(Number(e.target.value))}
                  />
                )}
                {settings && (
                  <p className="mt-1 text-xs text-slate-400">
                    Hard safety cap: {fmtInt(settings.maxUsersHardCap)} users.
                  </p>
                )}
                {overSingleMachine && settings && (
                  <div className="mt-2 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
                    <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                    <span>
                      {fmtInt(users)} users exceeds the ~
                      {fmtInt(settings.singleMachineRecommendedMax)} a single
                      machine can realistically generate. For tests this large,
                      use the distributed Locust cluster (see README).
                    </span>
                  </div>
                )}
              </div>

              <div>
                <label className="label">Ramp-up (users added per second)</label>
                <input
                  type="number"
                  className="input"
                  min={0.1}
                  step={1}
                  value={spawnRate}
                  onChange={(e) => setSpawnRate(Number(e.target.value))}
                />
                <p className="mt-1 text-xs text-slate-400">
                  Load increases gradually rather than all at once.
                </p>
              </div>

              <div>
                <label className="label">Duration</label>
                <select
                  className="input"
                  value={String(durationPreset)}
                  onChange={(e) =>
                    setDurationPreset(
                      e.target.value === "custom"
                        ? "custom"
                        : Number(e.target.value),
                    )
                  }
                >
                  {settings?.durationPresets.map((d) => (
                    <option key={d} value={d}>
                      {d < 60 ? `${d} seconds` : `${d / 60} minute(s)`}
                    </option>
                  ))}
                  <option value="custom">Custom…</option>
                </select>
                {durationPreset === "custom" && (
                  <input
                    type="number"
                    className="input mt-2"
                    min={1}
                    max={settings?.maxDurationHardCapS}
                    value={customDuration}
                    onChange={(e) => setCustomDuration(Number(e.target.value))}
                  />
                )}
                {settings && (
                  <p className="mt-1 text-xs text-slate-400">
                    Hard safety cap: {fmtInt(settings.maxDurationHardCapS)}s.
                  </p>
                )}
              </div>

              <div>
                <label className="label">Per-request timeout (seconds)</label>
                <input
                  type="number"
                  className="input"
                  min={1}
                  value={timeout}
                  onChange={(e) => setTimeoutS(Number(e.target.value))}
                />
              </div>
            </div>

            <h2 className="mb-3 mt-6 text-lg font-semibold">Scenario</h2>
            <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
              <div>
                <label className="label">HTTP method</label>
                <div className="flex gap-2">
                  {["GET", "HEAD"].map((m) => (
                    <button
                      key={m}
                      type="button"
                      onClick={() => setMethod(m)}
                      className={`btn ${
                        method === m ? "btn-primary" : "btn-ghost"
                      }`}
                    >
                      {m}
                    </button>
                  ))}
                </div>
                <label className="mt-4 flex items-center gap-2 text-sm text-slate-600">
                  <input
                    type="checkbox"
                    checked={allowPrivate}
                    onChange={(e) => setAllowPrivate(e.target.checked)}
                  />
                  Allow private / localhost targets (dev only)
                </label>
              </div>
              <div>
                <label className="label">Authorized paths (one per line)</label>
                <textarea
                  className="input h-28 font-mono text-xs"
                  value={pathsText}
                  onChange={(e) => setPathsText(e.target.value)}
                />
              </div>
            </div>

            <details className="mt-6 rounded-lg border border-slate-200 p-4">
              <summary className="cursor-pointer text-sm font-medium text-slate-700">
                Safety thresholds (automatic stop conditions)
              </summary>
              <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
                <Threshold
                  label="Max error rate (%)"
                  value={errThreshold}
                  onChange={setErrThreshold}
                />
                <Threshold
                  label="Max P95 latency (ms)"
                  value={p95Threshold}
                  step={100}
                  onChange={setP95Threshold}
                />
                <Threshold
                  label="Max HTTP 429 rate (%)"
                  value={rlThreshold}
                  onChange={setRlThreshold}
                />
                <Threshold
                  label="Max HTTP 5xx rate (%)"
                  value={seThreshold}
                  onChange={setSeThreshold}
                />
              </div>
            </details>

            <div className="mt-6 border-t border-slate-200 pt-5">
              <label className="flex items-start gap-3 text-sm text-slate-700">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={authorized}
                  onChange={(e) => setAuthorized(e.target.checked)}
                />
                <span>{AUTH_TEXT}</span>
              </label>
              <button
                className="btn-primary mt-4"
                disabled={!authorized || starting}
                onClick={handleStart}
              >
                <Play size={16} />
                {starting ? "Starting…" : "Start load test"}
              </button>
              {!authorized && (
                <p className="mt-2 text-xs text-slate-400">
                  You must confirm authorization before a test can start.
                </p>
              )}
            </div>
          </section>
        </>
      )}
    </div>
  );
}

function Threshold({
  label,
  value,
  onChange,
  step = 0.5,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  step?: number;
}) {
  return (
    <div>
      <label className="label">{label}</label>
      <input
        type="number"
        className="input"
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </div>
  );
}

function RunningView({
  current,
  onStop,
}: {
  current: CurrentTest;
  onStop: () => void;
}) {
  const m = current.metrics!;
  const cfg = current.config!;
  const progress = Math.min(
    (m.elapsedSeconds / cfg.durationSeconds) * 100,
    100,
  );
  return (
    <section className="space-y-5">
      <div className="card p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <span className="relative flex h-2.5 w-2.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500" />
              </span>
              <h2 className="text-lg font-semibold">Test running</h2>
            </div>
            <p className="mt-1 text-sm text-slate-500">
              {cfg.targetUrl} · peak {fmtInt(cfg.virtualUsers)} users ·{" "}
              {cfg.durationSeconds}s
            </p>
          </div>
          <button className="btn-danger" onClick={onStop}>
            <Square size={16} />
            STOP TEST
          </button>
        </div>
        <div className="mt-4 h-2 w-full overflow-hidden rounded-full bg-slate-100">
          <div
            className="h-full rounded-full bg-brand-500 transition-all"
            style={{ width: `${progress}%` }}
          />
        </div>
        <p className="mt-1 text-xs text-slate-400">
          Elapsed {Math.round(m.elapsedSeconds)}s / {cfg.durationSeconds}s
        </p>
      </div>

      <MetricGrid metrics={m} />
      <LiveCharts history={current.history ?? []} metrics={m} />
    </section>
  );
}

function SummaryView({ current }: { current: CurrentTest }) {
  const m = current.metrics!;
  const cfg = current.config!;
  return (
    <section className="card p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Last test summary</h2>
        <StatusBadge result={current.result!} />
      </div>
      {current.stopReason && (
        <div className="mt-3 rounded-lg bg-slate-50 px-4 py-2 text-sm text-slate-600">
          {current.stopReason}
        </div>
      )}
      <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricTile label="Target" value={cfg.targetUrl} />
        <MetricTile label="Peak users" value={fmtInt(cfg.virtualUsers)} />
        <MetricTile label="Total requests" value={fmtInt(m.totalRequests)} />
        <MetricTile label="Requests/sec" value={fmtNum(m.requestsPerSecond)} />
        <MetricTile label="Avg latency" value={fmtMs(m.avgLatencyMs)} />
        <MetricTile label="P95" value={fmtMs(m.p95Ms)} />
        <MetricTile label="P99" value={fmtMs(m.p99Ms)} />
        <MetricTile
          label="Error rate"
          value={`${fmtNum(m.errorRatePct, 2)}%`}
          accent={m.errorRatePct > 1 ? "warn" : "good"}
        />
      </div>
      <div className="mt-5">
        <LiveCharts history={current.history ?? []} metrics={m} />
      </div>
    </section>
  );
}

function MetricGrid({ metrics: m }: { metrics: import("@/lib/api").Metrics }) {
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <MetricTile label="Active users" value={fmtInt(m.activeUsers)} />
      <MetricTile label="Requests/sec" value={fmtNum(m.requestsPerSecond)} />
      <MetricTile label="Total requests" value={fmtInt(m.totalRequests)} />
      <MetricTile
        label="Error rate"
        value={`${fmtNum(m.errorRatePct, 2)}%`}
        accent={m.errorRatePct > 5 ? "bad" : m.errorRatePct > 1 ? "warn" : "good"}
      />
      <MetricTile label="Successful" value={fmtInt(m.successfulRequests)} accent="good" />
      <MetricTile label="Failed" value={fmtInt(m.failedRequests)} accent={m.failedRequests > 0 ? "warn" : "default"} />
      <MetricTile label="Avg latency" value={fmtMs(m.avgLatencyMs)} />
      <MetricTile label="Max latency" value={fmtMs(m.maxLatencyMs)} />
      <MetricTile label="P50" value={fmtMs(m.p50Ms)} />
      <MetricTile label="P95" value={fmtMs(m.p95Ms)} />
      <MetricTile label="P99" value={fmtMs(m.p99Ms)} />
      <MetricTile label="Min latency" value={fmtMs(m.minLatencyMs)} />
    </div>
  );
}
