export function MetricTile({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: "default" | "good" | "warn" | "bad";
}) {
  const color =
    accent === "good"
      ? "text-emerald-600"
      : accent === "warn"
        ? "text-amber-600"
        : accent === "bad"
          ? "text-red-600"
          : "text-slate-900";
  return (
    <div className="card px-4 py-3">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className={`mt-1 text-2xl font-semibold ${color}`}>{value}</div>
    </div>
  );
}
