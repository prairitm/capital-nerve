import clsx from "clsx";
import type { SeverityLevel } from "@/api/types";

/**
 * Materiality chip — answers "how much does this move the thesis?". Severity
 * is the underlying field but we relabel it as Materiality in the UI so it
 * is not confused with tone (POSITIVE / NEGATIVE / MIXED / NEUTRAL), which
 * lives on `SignalBadge`. Together the two chips replace any single
 * contradictory "Critical-risk + Positive" headline.
 */
const MAP: Record<SeverityLevel, { label: string; klass: string }> = {
  LOW: { label: "Routine", klass: "chip-low" },
  MEDIUM: { label: "Notable", klass: "chip-neutral" },
  HIGH: { label: "Material", klass: "chip-mixed" },
  CRITICAL: { label: "Market-moving", klass: "chip-negative" },
};

export function MaterialityBadge({
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
