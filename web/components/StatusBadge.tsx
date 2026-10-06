import { resultColor } from "@/lib/format";

export function StatusBadge({ result }: { result: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-3 py-1 text-sm font-semibold ${resultColor(
        result,
      )}`}
    >
      {result}
    </span>
  );
}
