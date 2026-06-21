import clsx from "clsx";
import type { MetricConfidenceBand } from "@/api/types";

interface Props {
  band: MetricConfidenceBand;
  score?: number | null;
  className?: string;
}

const BAND_TONE: Record<MetricConfidenceBand, string> = {
  high: "text-positive border-positive/30 bg-positive-bg",
  medium: "text-mixed border-mixed/40 bg-mixed-bg",
  low: "text-negative border-negative/40 bg-negative-bg",
};

const BAND_LABEL: Record<MetricConfidenceBand, string> = {
  high: "High",
  medium: "Medium",
  low: "Low",
};

/**
 * Confidence band for the metric's underlying extraction.
 *
 * The score is computed on the backend from the input extracted-value
 * confidences (see `services/pipeline/metrics.py`). We collapse it into a
 * three-band badge so an analyst can decide in one glance whether to
 * trust the metric before opening the calculation chain.
 */
export function MetricConfidenceBadge({ band, score, className }: Props) {
  const title =
    score != null
      ? `${BAND_LABEL[band]} confidence (${score.toFixed(0)} / 100)`
      : `${BAND_LABEL[band]} confidence`;
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] uppercase tracking-wider font-semibold",
        BAND_TONE[band],
        className,
      )}
      title={title}
    >
      {BAND_LABEL[band]} confidence
    </span>
  );
}
