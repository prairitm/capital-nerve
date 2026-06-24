import clsx from "clsx";
import type { SeverityLevel } from "@/api/types";

/** Materiality chip — how much a signal moves the thesis. Backend enum stays
 * LOW / MEDIUM / HIGH / CRITICAL; labels are Routine / Notable / Material /
 * Market-moving. */
const MAP: Record<SeverityLevel, { label: string; klass: string }> = {
  LOW: { label: "Routine", klass: "chip-low" },
  MEDIUM: { label: "Notable", klass: "chip-neutral" },
  HIGH: { label: "Material", klass: "chip-mixed" },
  CRITICAL: { label: "Market-moving", klass: "chip-negative" },
};

export function SeverityBadge({
  level,
  size = "sm",
}: {
  level: SeverityLevel | null | undefined;
  size?: "sm" | "md";
}) {
  if (!level) return null;
  const cfg = MAP[level];
  return (
    <span
      className={clsx(cfg.klass, size === "md" && "text-sm px-3 py-1.5")}
      title="Materiality — how much this signal moves the investment thesis."
    >
      <span className="size-1.5 rounded-full bg-current shrink-0" />
      {cfg.label}
    </span>
  );
}
