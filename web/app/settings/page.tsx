"use client";

import { useEffect, useState } from "react";
import { ShieldCheck } from "lucide-react";
import { api, type AppSettings } from "@/lib/api";
import { fmtInt, fmtNum } from "@/lib/format";
import { MetricTile } from "@/components/MetricTile";

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between border-b border-slate-100 py-3 last:border-0">
      <span className="text-sm text-slate-600">{label}</span>
      <span className="text-sm font-medium text-slate-900">{value}</span>
    </div>
  );
}

export default function SettingsPage() {
  const [s, setS] = useState<AppSettings | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .getSettings()
      .then(setS)
      .catch((e) => setError(String(e.message ?? e)));
  }, []);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-sm text-slate-500">
          Effective configuration for this local installation. Values are set via
          the backend&apos;s <code className="text-xs">.env</code> file.
        </p>
      </header>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {s && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
            <MetricTile label="Max users hard cap" value={fmtInt(s.maxUsersHardCap)} />
            <MetricTile label="Max duration cap" value={`${fmtInt(s.maxDurationHardCapS)} s`} />
            <MetricTile
              label="Single-machine advisory"
              value={fmtInt(s.singleMachineRecommendedMax)}
            />
          </div>

          <section className="card p-6">
            <h2 className="mb-2 text-lg font-semibold">Default test parameters</h2>
            <Row label="Default max users" value={fmtInt(s.defaultMaxUsers)} />
            <Row label="Default duration" value={`${fmtInt(s.defaultDurationS)} s`} />
            <Row label="Default ramp-up" value={`${fmtNum(s.defaultSpawnRate)} users/sec`} />
            <Row label="Default timeout" value={`${fmtNum(s.defaultTimeoutS)} s`} />
          </section>

          <section className="card p-6">
            <h2 className="mb-2 text-lg font-semibold">Default safety thresholds</h2>
            <Row label="Error-rate threshold" value={`${fmtNum(s.defaultErrorThresholdPct)} %`} />
            <Row label="P95 latency threshold" value={`${fmtInt(s.defaultP95ThresholdMs)} ms`} />
          </section>

          <section className="card p-6">
            <h2 className="mb-2 text-lg font-semibold">Policy &amp; storage</h2>
            <Row
              label="Allow private / localhost targets by default"
              value={s.allowPrivateTargets ? "Enabled" : "Blocked"}
            />
            <Row label="Database location" value={s.databasePath} />
          </section>

          <div className="flex items-start gap-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">
            <ShieldCheck size={18} className="mt-0.5 shrink-0" />
            <p>
              Hard caps are the outer safety envelope and are intentionally not
              editable from the UI. Change them via{" "}
              <code className="text-xs">LT_MAX_USERS_HARD_CAP</code> /{" "}
              <code className="text-xs">LT_MAX_DURATION_HARD_CAP_S</code> in the
              backend&apos;s <code className="text-xs">.env</code>.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
