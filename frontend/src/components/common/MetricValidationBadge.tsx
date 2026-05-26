import clsx from "clsx";
import { AlertTriangle, CheckCircle2, ShieldAlert } from "lucide-react";
import type { MetricValidationStatus } from "@/api/types";

interface Props {
  status: MetricValidationStatus;
  reason?: string | null;
  className?: string;
}

const STATUS_TONE: Record<MetricValidationStatus, string> = {
  validated: "text-positive border-positive/30 bg-positive-bg",
  anomaly: "text-mixed border-mixed/40 bg-mixed-bg",
  quarantined: "text-negative border-negative/40 bg-negative-bg",
};

const STATUS_LABEL: Record<MetricValidationStatus, string> = {
  validated: "Validated",
  anomaly: "Anomaly",
  quarantined: "Quarantined",
};

/**
 * Render the metric's validation state next to its value on the feed row.
 *
 * - `validated` is shown only on hover via the title (no badge in the strip)
 *   so a clean number does not gain visual weight.
 * - `anomaly` and `quarantined` are visible and carry the metric_anomaly /
 *   bounds explanation as a tooltip — analysts must be able to see the
 *   "I don't trust this" cue without leaving the feed.
 */
export function MetricValidationBadge({ status, reason, className }: Props) {
  if (status === "validated") return null;
  const Icon = status === "anomaly" ? AlertTriangle : ShieldAlert;
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] uppercase tracking-wider font-semibold",
        STATUS_TONE[status],
        className,
      )}
      title={reason || STATUS_LABEL[status]}
    >
      <Icon size={11} aria-hidden />
      {STATUS_LABEL[status]}
    </span>
  );
}

/** Inline icon-only mark for the "fine" case — used when the host strip
 *  wants to acknowledge the metric *was* checked. */
export function ValidatedTick({ className }: { className?: string }) {
  return (
    <CheckCircle2
      size={12}
      className={clsx("text-positive/70", className)}
      aria-hidden
    />
  );
}
