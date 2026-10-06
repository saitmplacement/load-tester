export function fmtInt(n: number): string {
  return n.toLocaleString("en-US", { maximumFractionDigits: 0 });
}

export function fmtNum(n: number, digits = 1): string {
  return n.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function fmtMs(n: number): string {
  if (n >= 1000) return `${fmtNum(n / 1000, 2)} s`;
  return `${Math.round(n)} ms`;
}

export function fmtDateTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString();
}

export function resultColor(result: string): string {
  switch (result) {
    case "PASSED":
      return "bg-emerald-100 text-emerald-700 border-emerald-200";
    case "WARNING":
      return "bg-amber-100 text-amber-700 border-amber-200";
    case "STOPPED":
      return "bg-red-100 text-red-700 border-red-200";
    case "FAILED":
      return "bg-rose-100 text-rose-700 border-rose-200";
    default:
      return "bg-slate-100 text-slate-700 border-slate-200";
  }
}
