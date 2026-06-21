import { useCallback, useMemo } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ChevronDown } from "lucide-react";
import clsx from "clsx";
import type { CardBrief } from "@/api/types";
import type { TimelineCardGroup } from "@/lib/cards";
import { EventSignalSummary } from "@/components/cards/EventSignalSummary";
import { IntelligenceCard } from "@/components/cards/IntelligenceCard";
import { IntelligenceFeedItem } from "@/components/cards/IntelligenceFeedItem";
import { SeverityBadge } from "@/components/common/SeverityBadge";
import { SignalBadge } from "@/components/common/SignalBadge";
import {
  formatDate,
  resolveEventDisplayTitle,
  resolveQuarterPeriodLabel,
  timelineDateKey,
} from "@/lib/format";

interface Props {
  groups: TimelineCardGroup[];
  /** When `variant="card"`, pass to open the drawer; otherwise cards navigate to `/intelligence/:id`. */
  onOpen?: (cardId: number) => void;
  onSaveWatchItem?: (card: CardBrief) => void;
  /** Show company name in the event header (market-wide feed). */
  showCompanyInHeader?: boolean;
  variant?: "feed" | "card";
}

interface DateSection {
  key: string;
  label: string;
  groups: TimelineCardGroup[];
}

const OTHER_DATE_KEY = "other";

function buildDateSections(groups: TimelineCardGroup[]): DateSection[] {
  const sections: DateSection[] = [];
  const indexByKey = new Map<string, number>();

  for (const group of groups) {
    const key =
      timelineDateKey(group.eventDate) ??
      timelineDateKey(group.cards[0]?.event_date) ??
      timelineDateKey(group.cards[0]?.created_at) ??
      OTHER_DATE_KEY;

    const idx = indexByKey.get(key);
    if (idx === undefined) {
      indexByKey.set(key, sections.length);
      sections.push({
        key,
        label: key === OTHER_DATE_KEY ? "Other updates" : formatDate(key),
        groups: [group],
      });
    } else {
      sections[idx].groups.push(group);
    }
  }

  return sections;
}

function TimelineEventHeader({
  group,
  showCompanyInHeader,
  showDateInHeader,
  expanded,
  expandable,
  onToggle,
  onOpenEvent,
}: {
  group: TimelineCardGroup;
  showCompanyInHeader: boolean;
  showDateInHeader: boolean;
  expanded: boolean;
  expandable: boolean;
  onToggle: () => void;
  onOpenEvent: () => void;
}) {
  const lead = group.cards[0];
  const symbol = lead?.company.nse_symbol || lead?.company.bse_code;
  const eventId = group.event?.event_id ?? lead?.event_id;
  const verdict = group.cards.find((c) => c.card_type === "result_verdict") ?? null;
  const signal = verdict?.signal_direction ?? group.event?.overall_signal ?? lead?.signal_direction ?? null;
  const severity = verdict?.severity ?? group.event?.overall_severity ?? lead?.severity ?? null;
  const eventType = group.eventType ?? lead?.event_type ?? null;
  const displayTitle = resolveEventDisplayTitle(eventType, group.eventLabel);
  const periodLabelRaw = resolveQuarterPeriodLabel(
    lead?.period ?? group.event?.period ?? null,
    group.eventLabel,
  );
  const periodLabel = periodLabelRaw === "Unknown period" ? null : periodLabelRaw;
  const canNavigate = Boolean(symbol && eventId);

  if (
    !group.eventDate &&
    !periodLabel &&
    !eventType &&
    !group.eventLabel &&
    !showCompanyInHeader
  ) {
    return null;
  }

  const verdictHeadline = verdict?.headline?.trim() || null;

  return (
    <div className="rounded-lg -mx-2 px-2 py-2.5 hover:bg-surface-2/60 transition-colors">
      <div className="flex items-start gap-2 min-w-0">
        {expandable && (
          <button
            type="button"
            onClick={onToggle}
            aria-expanded={expanded}
            aria-label={expanded ? "Collapse event cards" : "Expand event cards"}
            className="shrink-0 -ml-1 mt-1 rounded-md p-1 hover:bg-surface-2 text-ink-soft"
          >
            <ChevronDown
              size={14}
              className={clsx("transition-transform", !expanded && "-rotate-90")}
              aria-hidden
            />
          </button>
        )}
        <button
          type="button"
          onClick={onOpenEvent}
          disabled={!canNavigate}
          className={clsx(
            "flex-1 min-w-0 text-left",
            !canNavigate && "cursor-default",
          )}
        >
          <div className="space-y-1.5 min-w-0">
            {showDateInHeader && group.eventDate ? (
              <div className="text-[11px] uppercase tracking-wider text-ink-soft">
                <span className="shrink-0">{formatDate(group.eventDate)}</span>
              </div>
            ) : null}

            {showCompanyInHeader && lead ? (
              <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                <span className="text-sm font-semibold text-ink shrink-0">
                  {lead.company.short_name || lead.company.company_name}
                </span>
                {symbol && (
                  <span className="text-xs font-medium text-ink-soft tabular-nums shrink-0">{symbol}</span>
                )}
              </div>
            ) : null}

            {periodLabel ? (
              <p className="text-[11px] uppercase tracking-wider text-ink-soft">{periodLabel}</p>
            ) : null}

            {(eventType || group.eventLabel) && (
              <p className="text-sm font-medium text-ink leading-snug">{displayTitle}</p>
            )}

            {verdictHeadline && (
              <p className="text-sm text-ink-mute leading-snug">{verdictHeadline}</p>
            )}

            {(signal || severity) && (
              <div className="flex items-center gap-2 pt-0.5">
                {signal && <SignalBadge direction={signal} />}
                {severity && <SeverityBadge level={severity} />}
              </div>
            )}
          </div>
        </button>
      </div>

      {!expanded && expandable && (
        <EventSignalSummary cards={group.cards} className="mt-2 ml-6" />
      )}
    </div>
  );
}

const EXPANDED_QUERY_KEY = "expanded";

function expansionKey(group: TimelineCardGroup): string | null {
  const eventId = group.event?.event_id ?? group.cards[0]?.event_id ?? null;
  if (eventId != null) return `evt_${eventId}`;
  return null;
}

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

export function IntelligenceTimeline({
  groups,
  onOpen,
  onSaveWatchItem,
  showCompanyInHeader = false,
  variant = "feed",
}: Props) {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const dateSections = useMemo(() => buildDateSections(groups), [groups]);

  const expandedEvents = useMemo(
    () => parseExpandedParam(searchParams.get(EXPANDED_QUERY_KEY)),
    [searchParams],
  );

  const toggleEvent = useCallback(
    (key: string) => {
      const next = new Set(expandedEvents);
      if (next.has(key)) next.delete(key);
      else next.add(key);
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
    [expandedEvents, setSearchParams],
  );

  if (groups.length === 0) return null;

  const renderGroup = (group: TimelineCardGroup, showDateInHeader: boolean) => {
    const lead = group.cards[0];
    const symbol = lead?.company.nse_symbol || lead?.company.bse_code;
    const eventId = group.event?.event_id ?? lead?.event_id;
    const key = expansionKey(group);
    const expandable = key !== null && group.cards.length > 0;
    const expanded = !expandable || expandedEvents.has(key);

    return (
      <li key={group.key} className="ml-4">
        <span className="ui-dot" />
        <TimelineEventHeader
          group={group}
          showCompanyInHeader={showCompanyInHeader}
          showDateInHeader={showDateInHeader}
          expanded={expanded}
          expandable={expandable}
          onToggle={() => {
            if (key) toggleEvent(key);
          }}
          onOpenEvent={() => {
            if (symbol && eventId) navigate(`/company/${symbol}/event/${eventId}`);
          }}
        />
        {expanded && (
          <div
            className={clsx(
              "space-y-2",
              (group.eventType ||
                group.eventLabel ||
                showCompanyInHeader ||
                group.eventDate ||
                lead?.period) &&
                "mt-2",
            )}
          >
            {group.cards.map((c) =>
              variant === "card" ? (
                <IntelligenceCard
                  key={c.card_id}
                  card={c}
                  onOpen={onOpen}
                  showCompany={!showCompanyInHeader}
                  onSaveWatchItem={onSaveWatchItem}
                />
              ) : (
                <IntelligenceFeedItem
                  key={c.card_id}
                  card={c}
                  onSaveWatchItem={onSaveWatchItem}
                  showCompany={!showCompanyInHeader}
                />
              ),
            )}
          </div>
        )}
      </li>
    );
  };

  const useDateSections = dateSections.length > 1 || dateSections[0]?.key !== OTHER_DATE_KEY;

  if (!useDateSections) {
    const only = dateSections[0];
    return (
      <ol className="relative border-l border-line ml-2 space-y-6">
        {only.groups.map((group) => renderGroup(group, true))}
      </ol>
    );
  }

  return (
    <div className="space-y-5">
      {dateSections.map((section) => {
        const eventCount = section.groups.length;

        return (
          <section key={section.key}>
            <div className="flex w-full items-center gap-2 px-1 py-1.5">
              <span className="text-xs font-semibold uppercase tracking-wider text-ink">
                {section.label}
              </span>
              <span className="ml-auto text-[11px] text-ink-soft tabular-nums">
                {eventCount} {eventCount === 1 ? "event" : "events"}
              </span>
            </div>

            <ol className="relative border-l border-line ml-2 space-y-6 mt-3">
              {section.groups.map((group) => renderGroup(group, false))}
            </ol>
          </section>
        );
      })}
    </div>
  );
}
