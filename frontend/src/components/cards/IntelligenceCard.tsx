import { useNavigate } from "react-router-dom";
import { BookmarkPlus } from "lucide-react";
import type { CardBrief } from "@/api/types";
import { SourceDocumentLink } from "@/components/common/SourceDocumentLink";
import { SignalBadge } from "@/components/common/SignalBadge";
import { TriggerMetricStrip } from "@/components/cards/TriggerMetricStrip";
import {
  cardTypeLabel,
  formatDate,
  formatExtractionConfidence,
  relativeDate,
} from "@/lib/format";

interface Props {
  card: CardBrief;
  /** When set, opens the card drawer. Otherwise navigates to `/intelligence/:cardId`. */
  onOpen?: (id: number) => void;
  showCompany?: boolean;
  onSaveWatchItem?: (card: CardBrief) => void;
}

const COMPARATOR_HEADLINE_LABEL: Record<string, string> = {
  yoy: "YoY",
  qoq: "QoQ",
  yoy_and_qoq: "YoY · QoQ",
  pp_vs_prior_yoy: "Δ vs prior YoY",
};

/**
 * Honest comparator chip next to the card headline. Prefers an explicit
 * `trigger_metric.comparison_type`; falls back to inferring from the trigger
 * metric code suffix so cards built from legacy signals still get a label.
 */
function headlineComparator(card: CardBrief): string | null {
  const explicit = card.trigger_metric?.comparison_type;
  if (explicit && COMPARATOR_HEADLINE_LABEL[explicit]) {
    return COMPARATOR_HEADLINE_LABEL[explicit];
  }
  const code = card.trigger_metric?.code ?? null;
  if (!code) return null;
  if (code.includes("_yoy")) return COMPARATOR_HEADLINE_LABEL.yoy;
  if (code.includes("_qoq")) return COMPARATOR_HEADLINE_LABEL.qoq;
  return null;
}

export function IntelligenceCard({ card, onOpen, showCompany = true, onSaveWatchItem }: Props) {
  const navigate = useNavigate();
  const symbol = card.company.nse_symbol || card.company.bse_code;
  const comparator = headlineComparator(card);

  const openCard = () => {
    if (onOpen) onOpen(card.card_id);
    else navigate(`/intelligence/${card.card_id}`);
  };

  return (
    <article
      role="button"
      tabIndex={0}
      onClick={openCard}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          openCard();
        }
      }}
      className="group card rounded-xl border border-line/60 bg-surface-2/40 px-3 py-3 hover:border-line-strong hover:bg-surface-2 transition-colors h-full cursor-pointer"
    >
      <div className="flex flex-col gap-2.5 h-full min-w-0">
        <div className="text-[11px] uppercase tracking-wider text-ink-soft">
          {cardTypeLabel(card.card_type)}
        </div>

        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            {showCompany ? (
              <>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    if (symbol) navigate(`/company/${symbol}`);
                  }}
                  className="text-sm font-semibold text-ink hover:text-ink-mute text-left"
                >
                  {card.company.short_name || card.company.company_name}
                  {symbol && (
                    <span className="ml-1.5 text-xs font-normal text-ink-soft">{symbol}</span>
                  )}
                </button>
                <h3 className="text-[15px] font-medium text-ink leading-snug mt-0.5">
                  {card.headline}
                  {comparator && (
                    <span
                      className="ml-1.5 inline-flex items-center align-middle rounded-full border border-line/60 bg-surface-2/60 px-1.5 py-0 text-[10px] font-medium uppercase tracking-wider text-ink-soft"
                      title="Comparator used by the trigger metric"
                    >
                      {comparator}
                    </span>
                  )}
                </h3>
              </>
            ) : (
              <h3 className="text-[15px] font-semibold text-ink leading-snug">
                {card.headline}
                {comparator && (
                  <span
                    className="ml-1.5 inline-flex items-center align-middle rounded-full border border-line/60 bg-surface-2/60 px-1.5 py-0 text-[10px] font-medium uppercase tracking-wider text-ink-soft"
                    title="Comparator used by the trigger metric"
                  >
                    {comparator}
                  </span>
                )}
              </h3>
            )}
          </div>
          <SignalBadge direction={card.signal_direction} />
        </div>

        <p className="text-sm text-ink-mute leading-relaxed line-clamp-2 flex-1">
          {card.one_line_summary}
        </p>

        <TriggerMetricStrip metric={card.trigger_metric} documentId={card.document_id} />

        <div className="flex items-center justify-between gap-2 pt-0.5 mt-auto">
          <div className="text-xs text-ink-soft min-w-0 truncate">
            {card.document_id ? (
              <SourceDocumentLink
                documentId={card.document_id}
                label={card.source_label || "Source"}
                onClick={(e) => e.stopPropagation()}
              />
            ) : card.source_label ? (
              <span className="text-ink-mute truncate" title={card.source_label}>
                {card.source_label}
              </span>
            ) : null}
            {card.event_date && (
              <>
                {(card.document_id || card.source_label) && <span className="mx-1.5 text-line">·</span>}
                <span title={formatDate(card.event_date)}>{relativeDate(card.event_date)}</span>
              </>
            )}
            {card.confidence_score != null && (
              <>
                <span className="mx-1.5 text-line">·</span>
                <span title="Extraction confidence (0–100)">
                  {formatExtractionConfidence(card.confidence_score)} extraction
                </span>
              </>
            )}
          </div>
          {onSaveWatchItem && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onSaveWatchItem(card);
              }}
              title="Save as watch item"
              className="btn-ghost px-2 py-1 shrink-0"
            >
              <BookmarkPlus size={15} />
            </button>
          )}
        </div>
      </div>
    </article>
  );
}
