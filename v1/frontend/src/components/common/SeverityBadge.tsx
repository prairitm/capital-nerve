import clsx from "clsx";
import type { SeverityLevel } from "@/api/types";

/**
 * Materiality chip — rebranded from "Severity" so the UI never combines
 * "Critical-risk" with "Positive" tone. Backend enum stays
 * `LOW / MEDIUM / HIGH / CRITICAL`; user-facing labels are
 * `Routine / Notable / Material / Market-moving`.
 *
 * `MaterialityBadge` is the canonical name going forward; `SeverityBadge`
 * is kept as a compatibility alias so existing call sites pick up the new
 * vocabulary without a mechanical rename.
 */
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
