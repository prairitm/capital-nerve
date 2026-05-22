import { useNavigate } from "react-router-dom";
import { BookmarkPlus } from "lucide-react";
import type { CardBrief } from "@/api/types";
import { SourceDocumentLink } from "@/components/common/SourceDocumentLink";
import { SignalBadge } from "@/components/common/SignalBadge";
import { cardTypeLabel, formatDate, relativeDate } from "@/lib/format";

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
                </h3>
              </>
            ) : (
              <h3 className="text-[15px] font-semibold text-ink leading-snug">{card.headline}</h3>
            )}
          </div>
          <SignalBadge direction={card.signal_direction} />
        </div>

        <p className="text-sm text-ink-mute leading-relaxed line-clamp-2 flex-1">
          {card.one_line_summary}
        </p>

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
                <span>{Math.round(card.confidence_score)}% confidence</span>
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
