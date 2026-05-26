import type { ConfidenceLevel } from "@/api/types";
import { formatExtractionConfidence, normalizeConfidenceScore } from "@/lib/format";

/**
 * Card-level extraction confidence chip.
 *
 * Scores are stored on a 0–100 scale (`Numeric(5, 2)` in
 * `app.models.intelligence`). Label is explicit — analysts have asked us not
 * to conflate the trust of the extracted card with the trust of an individual
 * metric input. For per-metric trust use `MetricConfidenceBadge`.
 */
export function ConfidenceBadge({
  level,
  score,
}: {
  level?: ConfidenceLevel | null;
  score?: number | null;
}) {
  if (!level && score == null) return null;
  const normalized = normalizeConfidenceScore(score);
  const text =
    normalized != null
      ? `${formatExtractionConfidence(score)} extraction confidence`
      : level
        ? `${level.replace("_", " ").toLowerCase()} extraction confidence`
        : "";
  const klass =
    level === "HIGH" || (normalized != null && normalized >= 85)
      ? "chip-positive"
      : level === "MEDIUM" || (normalized != null && normalized >= 70)
        ? "chip-neutral"
        : "chip-low";
  return (
    <span className={klass} title="Extraction confidence (0–100)">
      {text}
    </span>
  );
}
