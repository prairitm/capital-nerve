import clsx from "clsx";
import type { SignalDirection } from "@/api/types";

const MAP: Record<SignalDirection, { label: string; klass: string }> = {
  POSITIVE: { label: "Positive", klass: "chip-positive" },
  NEGATIVE: { label: "Negative", klass: "chip-negative" },
  MIXED: { label: "Mixed", klass: "chip-mixed" },
  NEUTRAL: { label: "Neutral", klass: "chip-neutral" },
};

export function SignalBadge({
  direction,
  size = "sm",
}: {
  direction: SignalDirection | null | undefined;
  size?: "sm" | "md";
}) {
  if (!direction) return null;
  const cfg = MAP[direction];
  return (
    <span className={clsx(cfg.klass, size === "md" && "text-sm px-3 py-1.5")}>
      <span className="size-1.5 rounded-full bg-current" />
      {cfg.label}
    </span>
  );
}
