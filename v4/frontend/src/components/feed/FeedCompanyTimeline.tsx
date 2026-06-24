import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import type { CompanyFeedGroup } from "@/lib/events";
import { QuarterSignalsTimeline } from "@/components/feed/QuarterSignalsTimeline";

export function FeedCompanyTimeline({ group }: { group: CompanyFeedGroup }) {
  const ticker = group.company.ticker;

  if (!ticker || group.quarterGroups.length === 0) return null;

  return (
    <section className="card overflow-hidden">
      <div className="px-5 py-4 flex items-start justify-between gap-3 border-b border-line/60">
        <div className="min-w-0">
          <Link
            to={`/company/${ticker}`}
            className="text-lg font-semibold text-ink hover:text-ink-mute transition-colors"
          >
            {group.company.name}
          </Link>
          <div className="text-sm text-ink-mute mt-0.5">
            {ticker}
            {group.company.exchange && (
              <span className="text-ink-soft"> · {group.company.exchange}</span>
            )}
          </div>
        </div>
        <Link
          to={`/company/${ticker}`}
          className="text-xs text-ink-mute hover:text-ink inline-flex items-center gap-1 shrink-0"
        >
          {group.signals.length} {group.signals.length === 1 ? "signal" : "signals"}
          <ChevronRight size={13} />
        </Link>
      </div>

      <QuarterSignalsTimeline
        quarterGroups={group.quarterGroups}
        ticker={ticker}
        collapsible={group.quarterGroups.length > 1}
      />
    </section>
  );
}
