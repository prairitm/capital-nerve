import clsx from "clsx";
import type { MetricKind } from "@/api/types";

interface Props {
  kind: MetricKind | null | undefined;
  className?: string;
}

const KIND_LABEL: Record<MetricKind, string> = {
  financial: "Financial",
  model_score: "Model score",
  composite: "Composite",
};

// Tones are intentionally muted — the badge is a typography cue, not a
// signal-direction cue, and must not compete with `SignalBadge`.
const KIND_TONE: Record<MetricKind, string> = {
  financial: "text-positive/90 border-positive/30 bg-positive-bg/60",
  model_score: "text-mixed/90 border-mixed/30 bg-mixed-bg/60",
  composite: "text-ink-mute border-line bg-surface-2",
};

/**
 * Surfaces the metric ontology (Financial / Model score / Composite) so an
 * analyst can tell at a glance whether a feed-row number is a derived ratio,
 * a concall lexicon score (0–100), or a metric of metrics. Returns `null`
 * when the kind is unknown so callers can render without conditional gating.
 */
export function MetricKindBadge({ kind, className }: Props) {
  if (!kind) return null;
  return (
    <span
      className={clsx(
        "inline-flex items-center rounded-md border px-1.5 py-0.5 text-[10px] uppercase tracking-wider font-semibold",
        KIND_TONE[kind],
        className,
      )}
      title={KIND_LABEL[kind]}
    >
      {KIND_LABEL[kind]}
    </span>
  );
}
