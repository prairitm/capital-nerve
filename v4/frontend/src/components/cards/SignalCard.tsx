import { useNavigate } from "react-router-dom";
import { SignalBadge } from "@/components/common/SignalBadge";
import { formatNumber } from "@/lib/format";
import type { FeedRow } from "@/lib/signals";

interface Props {
  row: FeedRow;
  showCompany?: boolean;
}

/** Feed / signal card. Forked from v1's IntelligenceFeedItem chrome but driven
 * by the narrow `FeedRow` shape derived from a 7-step signal. */
export function SignalCard({ row, showCompany = true }: Props) {
  const navigate = useNavigate();
  const triggerEntries = Object.entries(row.triggerValues);

  return (
    <article
      role="button"
      tabIndex={0}
      onClick={() => navigate(`/signals/${row.id}`)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          navigate(`/signals/${row.id}`);
        }
      }}
      className="group rounded-xl border border-line/60 bg-surface-2/40 px-3.5 py-3 hover:border-line-strong hover:bg-surface-2 transition-colors cursor-pointer"
    >
      <div className="min-w-0 space-y-2.5">
        <div className="flex items-center justify-between gap-3">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-soft">
            {row.categoryLabel}
          </span>
          <SignalBadge direction={row.direction} />
        </div>

        <div className="space-y-1 min-w-0">
          {showCompany && row.companyName && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                if (row.companyTicker) navigate(`/company/${row.companyTicker}`);
              }}
              className="text-xs font-medium text-ink-soft hover:text-ink text-left transition-colors"
            >
              {row.companyName}
              {row.companyTicker && (
                <span className="ml-1.5 font-normal text-ink-mute">{row.companyTicker}</span>
              )}
            </button>
          )}
          <h3 className="text-[15px] font-semibold text-ink leading-snug">{row.headline}</h3>
          {row.summary && (
            <p className="text-sm text-ink-mute leading-relaxed line-clamp-2">{row.summary}</p>
          )}
        </div>

        {triggerEntries.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {triggerEntries.map(([key, value]) => (
              <span
                key={key}
                className="rounded-lg bg-surface-3/60 border border-line/50 px-2 py-1 text-[11px] num text-ink-mute"
              >
                <span className="text-ink-soft">{key}</span>{" "}
                <span className="text-ink font-medium">{formatNumber(value, 2)}</span>
              </span>
            ))}
          </div>
        )}

      </div>
    </article>
  );
}
