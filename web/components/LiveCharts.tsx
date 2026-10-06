"use client";

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { HistoryPoint, Metrics } from "@/lib/api";

function ChartCard({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="card p-4">
      <div className="mb-2 text-sm font-medium text-slate-700">{title}</div>
      <div className="h-48 w-full">
        <ResponsiveContainer width="100%" height="100%">
          {children as React.ReactElement}
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function LineArea({
  data,
  dataKey,
  color,
  unit,
}: {
  data: HistoryPoint[];
  dataKey: keyof HistoryPoint;
  color: string;
  unit?: string;
}) {
  return (
    <AreaChart data={data} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
      <defs>
        <linearGradient id={`g-${dataKey}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="5%" stopColor={color} stopOpacity={0.35} />
          <stop offset="95%" stopColor={color} stopOpacity={0} />
        </linearGradient>
      </defs>
      <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
      <XAxis
        dataKey="t"
        tick={{ fontSize: 11, fill: "#94a3b8" }}
        tickFormatter={(v) => `${v}s`}
      />
      <YAxis tick={{ fontSize: 11, fill: "#94a3b8" }} width={40} />
      <Tooltip
        formatter={(v: number) => [`${v}${unit ?? ""}`, ""]}
        labelFormatter={(l) => `t=${l}s`}
      />
      <Area
        type="monotone"
        dataKey={dataKey}
        stroke={color}
        strokeWidth={2}
        fill={`url(#g-${dataKey})`}
        isAnimationActive={false}
      />
    </AreaChart>
  );
}

const STATUS_COLORS: Record<string, string> = {
  "2": "#10b981",
  "3": "#3b82f6",
  "4": "#f59e0b",
  "5": "#ef4444",
  "0": "#64748b",
};

function statusColor(code: string): string {
  if (code === "0") return STATUS_COLORS["0"];
  return STATUS_COLORS[code[0]] ?? "#64748b";
}

export function LiveCharts({
  history,
  metrics,
}: {
  history: HistoryPoint[];
  metrics: Metrics;
}) {
  const statusData = Object.entries(metrics.statusDistribution).map(
    ([code, count]) => ({
      code: code === "0" ? "error" : code,
      raw: code,
      count,
    }),
  );

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <ChartCard title="Requests / sec">
        <LineArea data={history} dataKey="rps" color="#2f72f5" />
      </ChartCard>
      <ChartCard title="Avg response time (ms)">
        <LineArea data={history} dataKey="avgMs" color="#8b5cf6" unit=" ms" />
      </ChartCard>
      <ChartCard title="P95 latency (ms)">
        <LineArea data={history} dataKey="p95Ms" color="#ec4899" unit=" ms" />
      </ChartCard>
      <ChartCard title="Error rate (%)">
        <LineArea data={history} dataKey="errorRatePct" color="#ef4444" unit="%" />
      </ChartCard>
      <ChartCard title="Active virtual users">
        <LineArea data={history} dataKey="activeUsers" color="#10b981" />
      </ChartCard>
      <ChartCard title="HTTP status distribution">
        <BarChart data={statusData} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
          <XAxis dataKey="code" tick={{ fontSize: 11, fill: "#94a3b8" }} />
          <YAxis tick={{ fontSize: 11, fill: "#94a3b8" }} width={40} />
          <Tooltip />
          <Bar dataKey="count" isAnimationActive={false} radius={[4, 4, 0, 0]}>
            {statusData.map((d) => (
              <Cell key={d.raw} fill={statusColor(d.raw)} />
            ))}
          </Bar>
        </BarChart>
      </ChartCard>
    </div>
  );
}
