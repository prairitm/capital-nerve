import clsx from "clsx";
import { ShieldAlert, TrendingDown, TrendingUp, Minus, AlertTriangle } from "lucide-react";
import type { CardBrief, SignalDirection } from "@/api/types";

interface Props {
  cards: CardBrief[];
  /** Soft cap on the number of chips shown. Default 5 (matches spec). */
  limit?: number;
  className?: string;
}

const DIRECTION_TONE: Record<SignalDirection, string> = {
  POSITIVE: "text-positive border-positive/30 bg-positive-bg",
  NEGATIVE: "text-negative border-negative/30 bg-negative-bg",
  MIXED: "text-mixed border-mixed/30 bg-mixed-bg",
  NEUTRAL: "text-neutral border-neutral/30 bg-neutral-bg",
};

const FALLBACK_TONE = "text-ink-mute border-line bg-surface-2";

function DirectionIcon({ direction }: { direction: SignalDirection | null }) {
  switch (direction) {
    case "POSITIVE":
      return <TrendingUp size={11} aria-hidden />;
    case "NEGATIVE":
      return <TrendingDown size={11} aria-hidden />;
    case "MIXED":
      return <AlertTriangle size={11} aria-hidden />;
    default:
      return <Minus size={11} aria-hidden />;
  }
}

/**
 * Compact strip of "what fired" chips for an event group, intended for the
 * collapsed accordion state on `IntelligenceTimeline`. Each chip pulls the
 * card headline (already a one-line signal label) and tones the colour by
 * the card's signal direction. When the underlying primary metric was
 * anomaly-flagged or quarantined we layer an inline icon onto the chip so
 * a reviewer can see the trust issue without expanding the event.
 */
export function EventSignalSummary({ cards, limit = 5, className }: Props) {
  const summaryCards = cards
    .filter((c) => c.card_type !== "result_verdict")
    .slice(0, limit);

  if (summaryCards.length === 0) return null;

  return (
    <div className={clsx("flex flex-wrap items-center gap-1.5", className)}>
      {summaryCards.map((c) => {
        const status = c.trigger_metric?.validation_status;
        const flagged = status === "anomaly" || status === "quarantined";
        return (
          <span
            key={c.card_id}
            className={clsx(
              "chip max-w-[18rem] truncate",
              DIRECTION_TONE[c.signal_direction ?? "NEUTRAL"] ?? FALLBACK_TONE,
              flagged && "ring-1 ring-mixed/40",
            )}
            title={
              flagged && c.trigger_metric?.validation_reason
                ? `${c.headline} — ${c.trigger_metric.validation_reason}`
                : c.headline
            }
          >
            <DirectionIcon direction={c.signal_direction ?? null} />
            <span className="truncate">{c.headline}</span>
            {flagged && <ShieldAlert size={11} className="text-mixed" aria-hidden />}
          </span>
        );
      })}
      {cards.length - summaryCards.length > 0 && (
        <span className="chip-low text-[11px]">
          +{cards.length - summaryCards.length} more
        </span>
      )}
    </div>
  );
}
