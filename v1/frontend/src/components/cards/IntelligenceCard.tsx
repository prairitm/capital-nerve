import { useNavigate } from "react-router-dom";
import { BookmarkPlus } from "lucide-react";
import type { CardBrief } from "@/api/types";
import { SourceDocumentLink } from "@/components/common/SourceDocumentLink";
import { SignalBadge } from "@/components/common/SignalBadge";
import { TriggerMetricStrip } from "@/components/cards/TriggerMetricStrip";
import {
  cardTypeLabel,
  cleanCardSummary,
  formatDate,
  relativeDate,
} from "@/lib/format";

interface Props {
  card: CardBrief;
  /** When set, opens the card drawer. Otherwise navigates to `/intelligence/:cardId`. */
  onOpen?: (id: number) => void;
  showCompany?: boolean;
  onSaveWatchItem?: (card: CardBrief) => void;
}

export function IntelligenceCard({ card, onOpen, showCompany = true, onSaveWatchItem }: Props) {
  const navigate = useNavigate();
  const symbol = card.company.nse_symbol || card.company.bse_code;
  const summary = cleanCardSummary(card.one_line_summary);
  const hasMetric = Boolean(card.trigger_metric?.name || card.trigger_metric?.value_display);

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
      className="group card rounded-xl border border-line/60 bg-surface-2/40 px-4 py-3.5 hover:border-line-strong hover:bg-surface-2 transition-colors h-full cursor-pointer"
    >
      <div className="flex flex-col gap-3 h-full min-w-0">
        <div className="flex items-center justify-between gap-3">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-soft">
            {cardTypeLabel(card.card_type)}
          </span>
          <SignalBadge direction={card.signal_direction} />
        </div>

        <div className="space-y-1 min-w-0">
          {showCompany && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                if (symbol) navigate(`/company/${symbol}`);
              }}
              className="text-xs font-medium text-ink-soft hover:text-ink text-left transition-colors"
            >
              {card.company.short_name || card.company.company_name}
              {symbol && (
                <span className="ml-1.5 font-normal text-ink-mute">{symbol}</span>
              )}
            </button>
          )}
          <h3 className="text-base font-semibold text-ink leading-snug tracking-tight">
            {card.headline}
          </h3>
          {summary && (
            <p className="text-sm text-ink-mute leading-relaxed line-clamp-2">{summary}</p>
          )}
        </div>

        {hasMetric && (
          <TriggerMetricStrip
            metric={card.trigger_metric}
            documentId={card.document_id}
            variant="highlight"
          />
        )}

        <div className="flex items-center justify-between gap-2 pt-2 mt-auto border-t border-line/40">
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
          </div>
          {onSaveWatchItem && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onSaveWatchItem(card);
              }}
              title="Save as watch item"
              className="btn-ghost px-2 py-1 shrink-0 opacity-80 group-hover:opacity-100"
            >
              <BookmarkPlus size={15} />
            </button>
          )}
        </div>
      </div>
    </article>
  );
}
