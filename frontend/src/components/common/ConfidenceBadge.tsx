import type { ConfidenceLevel } from "@/api/types";

export function ConfidenceBadge({
  level,
  score,
}: {
  level?: ConfidenceLevel | null;
  score?: number | null;
}) {
  if (!level && !score) return null;
  const text =
    score !== undefined && score !== null
      ? `${score.toFixed(0)}% confidence`
      : level
        ? `${level.replace("_", " ").toLowerCase()} confidence`
        : "";
  const klass =
    level === "HIGH" || (score !== undefined && score !== null && score >= 85)
      ? "chip-positive"
      : level === "MEDIUM" || (score !== undefined && score !== null && score >= 70)
        ? "chip-neutral"
        : "chip-low";
  return <span className={klass}>{text}</span>;
}
