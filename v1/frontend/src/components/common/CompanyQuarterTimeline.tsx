import { useCallback, useMemo } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ChevronDown } from "lucide-react";
import clsx from "clsx";
import { SignalBadge } from "@/components/common/SignalBadge";
import { SeverityBadge } from "@/components/common/SeverityBadge";
import { groupEventsByQuarter, type QuarterTimelineEvent } from "@/lib/cards";
import { formatDate, resolveEventDisplayTitle } from "@/lib/format";

interface Props<T extends QuarterTimelineEvent> {
  events: T[];
  symbol: string;
  /** Highlight the newest event row (typically the lead event in the latest quarter). */
  latestEventId?: number | null;
  /** Collapse older quarters when there are multiple sections. */
  collapsible?: boolean;
  summaryLineClamp?: boolean;
  /** Show only the N most recent quarters (all events in those quarters are kept). */
  maxQuarters?: number;
}

const EXPANDED_QUERY_KEY = "expanded";

function parseExpandedParam(value: string | null): Set<string> {
  if (!value) return new Set();
  return new Set(
    value
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean),
  );
}

function serializeExpanded(set: Set<string>): string {
  return [...set].sort().join(",");
}

export function CompanyQuarterTimeline<T extends QuarterTimelineEvent>({
  events,
  symbol,
  latestEventId = null,
  collapsible = true,
  summaryLineClamp = false,
  maxQuarters,
}: Props<T>) {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const quarterGroups = useMemo(() => {
    const groups = groupEventsByQuarter(events);
    return maxQuarters != null ? groups.slice(0, maxQuarters) : groups;
  }, [events, maxQuarters]);

  const expandedKeys = useMemo(
    () => parseExpandedParam(searchParams.get(EXPANDED_QUERY_KEY)),
    [searchParams],
  );

  const setKey = useCallback(
    (key: string, expanded: boolean) => {
      const next = new Set(expandedKeys);
      if (expanded) next.add(key);
      else next.delete(key);
      setSearchParams(
        (prev) => {
          const params = new URLSearchParams(prev);
          const serialized = serializeExpanded(next);
          if (serialized) params.set(EXPANDED_QUERY_KEY, serialized);
          else params.delete(EXPANDED_QUERY_KEY);
          return params;
        },
        { replace: true },
      );
    },
    [expandedKeys, setSearchParams],
  );

  if (quarterGroups.length === 0) return null;

  const latestQuarterKey = quarterGroups[0]?.key ?? null;

  const toggleQuarter = (key: string) => {
    const isExpanded = expandedKeys.has(key) || key === latestQuarterKey;
    setKey(key, !isExpanded);
  };

  return (
    <div className="space-y-5">
      {quarterGroups.map((group) => {
        const isLatestQuarter = group.key === latestQuarterKey;
        const expanded =
          !collapsible || expandedKeys.has(group.key) || isLatestQuarter;
        const lead = group.events[0];

        return (
          <section key={group.key}>
            {collapsible && quarterGroups.length > 1 ? (
              <button
                type="button"
                onClick={() => toggleQuarter(group.key)}
                aria-expanded={expanded}
                className={clsx(
                  "flex w-full items-center gap-2 rounded-lg -mx-1 px-1 py-1.5 text-left transition-colors",
                  isLatestQuarter ? "bg-surface-2/60" : "hover:bg-surface-2/50",
                )}
              >
                <ChevronDown
                  size={16}
                  className={clsx(
                    "shrink-0 text-ink-soft transition-transform duration-200",
                    !expanded && "-rotate-90",
                  )}
                  aria-hidden
                />
                <span className="text-xs font-semibold uppercase tracking-wider text-ink">
                  {group.label}
                </span>
                <span className="ml-auto text-[11px] text-ink-soft tabular-nums">
                  {group.events.length} {group.events.length === 1 ? "event" : "events"}
                </span>
              </button>
            ) : (
              <div
                className={clsx(
                  "flex items-baseline justify-between gap-2 px-1 py-1.5",
                  isLatestQuarter && "bg-surface-2/60 rounded-lg -mx-1",
                )}
              >
                <span className="text-xs font-semibold uppercase tracking-wider text-ink">
                  {group.label}
                </span>
                <span className="text-[11px] text-ink-soft tabular-nums shrink-0">
                  {group.events.length} {group.events.length === 1 ? "event" : "events"}
                </span>
              </div>
            )}

            {expanded && (
              <ol className="relative border-l border-line ml-2 mt-2 space-y-3">
                {group.events.map((ev) => {
                  const isLatest = ev.event_id === latestEventId;
                  const displayTitle = resolveEventDisplayTitle(ev.event_type, ev.event_title);
                  return (
                    <li key={ev.event_id} className="ml-4">
                      <span
                        className={clsx(
                          "ui-dot",
                          isLatest && "bg-brand ring-2 ring-brand/30",
                        )}
                      />
                      <button
                        type="button"
                        onClick={() => navigate(`/company/${symbol}/event/${ev.event_id}`)}
                        className={clsx(
                          "w-full text-left rounded-lg -mx-2 px-2 py-1 transition-colors",
                          isLatest ? "bg-surface-2/60" : "hover:bg-surface-2/40",
                        )}
                      >
                        <span className="text-[11px] uppercase tracking-wider text-ink-soft">
                          {formatDate(ev.event_date)}
                        </span>
                        <div className="font-medium mt-1">{displayTitle}</div>
                        {(ev.overall_signal || ev.overall_severity) && (
                          <div className="flex items-center gap-2 mt-1.5">
                            {ev.overall_signal && (
                              <SignalBadge direction={ev.overall_signal} />
                            )}
                            {ev.overall_severity && (
                              <SeverityBadge level={ev.overall_severity} />
                            )}
                          </div>
                        )}
                        {ev.summary_text && (
                          <p
                            className={clsx(
                              "text-xs text-ink-mute mt-2",
                              summaryLineClamp && "line-clamp-2",
                            )}
                          >
                            {ev.summary_text}
                          </p>
                        )}
                      </button>
                    </li>
                  );
                })}
              </ol>
            )}

            {!expanded && lead && (lead.overall_signal || lead.overall_severity) && (
              <div className="flex items-center gap-2 mt-1 ml-1">
                {lead.overall_signal && <SignalBadge direction={lead.overall_signal} />}
                {lead.overall_severity && <SeverityBadge level={lead.overall_severity} />}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}
