import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronDown } from "lucide-react";
import clsx from "clsx";
import type { MetricValue } from "@/api/types";
import type { FeedTimelineEvent, QuarterEventGroup } from "@/lib/events";
import { CompactSignalRow } from "@/components/signals/CompactSignalRow";
import { eventTypeLabel, formatDate, resolveEventDisplayTitle } from "@/lib/format";

function FeedEventBlock({
  event,
  ticker,
  metrics,
}: {
  event: FeedTimelineEvent;
  ticker: string;
  metrics?: MetricValue[];
}) {
  const navigate = useNavigate();
  const displayTitle = resolveEventDisplayTitle(event.event_type, event.title);

  if (event.signals.length === 0) return null;

  return (
    <div className="border-t border-line/40 first:border-t-0">
      <button
        type="button"
        onClick={() => navigate(`/company/${ticker}/event/${event.id}`)}
        className="w-full text-left px-5 py-2.5 hover:bg-surface-2/30 transition-colors"
      >
        <div className="text-[11px] uppercase tracking-wider text-ink-soft">
          {formatDate(event.event_date)}
          <span className="mx-1.5 text-ink-soft/50">·</span>
          {eventTypeLabel(event.event_type)}
        </div>
        <div className="text-sm font-medium text-ink mt-0.5">{displayTitle}</div>
      </button>
      <div className="divide-y divide-line/30 border-t border-line/30">
        {event.signals.map((signal) => (
          <CompactSignalRow key={signal.id} signal={signal} metrics={metrics} />
        ))}
      </div>
    </div>
  );
}

interface Props {
  quarterGroups: QuarterEventGroup<FeedTimelineEvent>[];
  ticker: string;
  metrics?: MetricValue[];
  collapsible?: boolean;
}

export function QuarterSignalsTimeline({
  quarterGroups,
  ticker,
  metrics = [],
  collapsible = true,
}: Props) {
  const [collapsedQuarters, setCollapsedQuarters] = useState<Set<string>>(() => new Set());
  const showCollapsible = collapsible && quarterGroups.length > 1;

  if (quarterGroups.length === 0) return null;

  const toggleQuarter = (key: string) => {
    setCollapsedQuarters((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  return (
    <>
      {quarterGroups.map((quarter, qi) => {
        const isLatest = qi === 0;
        const expanded = isLatest || !collapsedQuarters.has(quarter.key);

        return (
          <div key={quarter.key} className="border-t border-line/40 first:border-t-0">
            {showCollapsible ? (
              <button
                type="button"
                onClick={() => toggleQuarter(quarter.key)}
                aria-expanded={expanded}
                className={clsx(
                  "w-full flex items-center gap-2 px-5 py-2.5 text-left transition-colors",
                  isLatest ? "bg-surface-2/50" : "hover:bg-surface-2/30",
                )}
              >
                <ChevronDown
                  size={14}
                  className={clsx(
                    "shrink-0 text-ink-soft transition-transform",
                    !expanded && "-rotate-90",
                  )}
                  aria-hidden
                />
                <span className="text-xs font-semibold uppercase tracking-wider text-ink">
                  {quarter.label}
                </span>
                <span className="ml-auto text-[11px] text-ink-soft tabular-nums">
                  {quarter.events.length} {quarter.events.length === 1 ? "event" : "events"}
                </span>
              </button>
            ) : (
              <div
                className={clsx(
                  "flex items-baseline justify-between gap-2 px-5 py-2.5",
                  isLatest && "bg-surface-2/50",
                )}
              >
                <span className="text-xs font-semibold uppercase tracking-wider text-ink">
                  {quarter.label}
                </span>
                <span className="text-[11px] text-ink-soft tabular-nums shrink-0">
                  {quarter.events.length} {quarter.events.length === 1 ? "event" : "events"}
                </span>
              </div>
            )}

            {expanded &&
              quarter.events.map((event) => (
                <FeedEventBlock
                  key={event.id}
                  event={event}
                  ticker={ticker}
                  metrics={metrics}
                />
              ))}
          </div>
        );
      })}
    </>
  );
}
