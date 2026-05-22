import clsx from "clsx";
import type { SeverityLevel } from "@/api/types";

const MAP: Record<SeverityLevel, { label: string; klass: string }> = {
  LOW: { label: "Low", klass: "chip-low" },
  MEDIUM: { label: "Medium", klass: "chip-mixed" },
  HIGH: { label: "High", klass: "chip-negative" },
  CRITICAL: { label: "Critical", klass: "chip-negative" },
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
    <span className={clsx(cfg.klass, size === "md" && "text-sm px-3 py-1.5")}>
      <span className="size-1.5 rounded-full bg-current shrink-0" />
      {cfg.label}
    </span>
  );
}
