// Typed client for the FastAPI backend. All calls go through the same-origin
// /api proxy configured in next.config.mjs.

export interface AppSettings {
  maxUsersHardCap: number;
  maxDurationHardCapS: number;
  singleMachineRecommendedMax: number;
  defaultMaxUsers: number;
  defaultDurationS: number;
  defaultSpawnRate: number;
  defaultTimeoutS: number;
  defaultErrorThresholdPct: number;
  defaultP95ThresholdMs: number;
  allowPrivateTargets: boolean;
  databasePath: string;
  userPresets: number[];
  durationPresets: number[];
}

export interface Metrics {
  activeUsers: number;
  totalRequests: number;
  successfulRequests: number;
  failedRequests: number;
  requestsPerSecond: number;
  errorRatePct: number;
  avgLatencyMs: number;
  minLatencyMs: number;
  maxLatencyMs: number;
  p50Ms: number;
  p95Ms: number;
  p99Ms: number;
  statusDistribution: Record<string, number>;
  elapsedSeconds: number;
}

export interface HistoryPoint {
  t: number;
  rps: number;
  p95Ms: number;
  avgMs: number;
  errorRatePct: number;
  activeUsers: number;
}

export interface TestConfigView {
  targetUrl: string;
  virtualUsers: number;
  spawnRate: number;
  durationSeconds: number;
  method: string;
  paths: string[];
}

export interface CurrentTest {
  exists: boolean;
  running?: boolean;
  config?: TestConfigView;
  metrics?: Metrics;
  history?: HistoryPoint[];
  result?: string | null;
  stopReason?: string | null;
  savedId?: number | null;
}

export interface StartRequest {
  target_url: string;
  paths: string[];
  method: string;
  virtual_users: number;
  spawn_rate: number;
  duration_seconds: number;
  request_timeout_s: number;
  allow_private_targets: boolean;
  authorized: boolean;
  max_error_rate_pct: number;
  max_p95_latency_ms: number;
  max_rate_limit_pct: number;
  max_server_error_pct: number;
}

export interface TestSummary {
  id: number;
  targetUrl: string;
  startTime: string;
  endTime: string;
  durationSeconds: number;
  maxUsers: number;
  totalRequests: number;
  successfulRequests: number;
  failedRequests: number;
  requestsPerSecond: number;
  avgLatencyMs: number;
  minLatencyMs: number;
  maxLatencyMs: number;
  p50Ms: number;
  p95Ms: number;
  p99Ms: number;
  errorRatePct: number;
  result: string;
  stopReason: string;
}

async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* ignore parse errors */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  async getSettings(): Promise<AppSettings> {
    return jsonOrThrow(await fetch("/api/settings", { cache: "no-store" }));
  },

  async validate(
    url: string,
    allowPrivate: boolean,
  ): Promise<{ ok: boolean; message: string; normalizedUrl: string }> {
    return jsonOrThrow(
      await fetch("/api/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, allow_private: allowPrivate }),
      }),
    );
  },

  async startTest(req: StartRequest): Promise<{ clamped: Record<string, number> }> {
    return jsonOrThrow(
      await fetch("/api/tests", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req),
      }),
    );
  },

  async current(): Promise<CurrentTest> {
    return jsonOrThrow(await fetch("/api/tests/current", { cache: "no-store" }));
  },

  async stop(): Promise<void> {
    await jsonOrThrow(await fetch("/api/tests/stop", { method: "POST" }));
  },

  async history(): Promise<TestSummary[]> {
    return jsonOrThrow(await fetch("/api/history", { cache: "no-store" }));
  },

  async deleteHistory(id: number): Promise<void> {
    await jsonOrThrow(await fetch(`/api/history/${id}`, { method: "DELETE" }));
  },

  async clearHistory(): Promise<void> {
    await jsonOrThrow(await fetch("/api/history", { method: "DELETE" }));
  },

  exportUrl(format: "csv" | "json", id?: number): string {
    const q = new URLSearchParams({ format });
    if (id != null) q.set("id", String(id));
    return `/api/history/export?${q.toString()}`;
  },
};
