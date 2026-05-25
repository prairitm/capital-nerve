import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronDown } from "lucide-react";
import clsx from "clsx";
import type { CardBrief } from "@/api/types";
import type { TimelineCardGroup } from "@/lib/cards";
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
  onNavigate,
}: {
  group: TimelineCardGroup;
  showCompanyInHeader: boolean;
  showDateInHeader: boolean;
  onNavigate: () => void;
}) {
  const lead = group.cards[0];
  const symbol = lead?.company.nse_symbol || lead?.company.bse_code;
  const eventId = group.event?.event_id ?? lead?.event_id;
  const signal = group.event?.overall_signal ?? lead?.signal_direction;
  const severity = group.event?.overall_severity ?? lead?.severity;
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

  return (
    <button
      type="button"
      onClick={onNavigate}
      disabled={!canNavigate}
      className={clsx(
        "w-full text-left rounded-lg -mx-2 px-2 py-2.5 transition-colors",
        canNavigate && "hover:bg-surface-2/70",
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

        {(signal || severity) && (
          <div className="flex items-center gap-2 pt-0.5">
            {signal && <SignalBadge direction={signal} />}
            {severity && <SeverityBadge level={severity} />}
          </div>
        )}
      </div>
    </button>
  );
}

export function IntelligenceTimeline({
  groups,
  onOpen,
  onSaveWatchItem,
  showCompanyInHeader = false,
  variant = "feed",
}: Props) {
  const navigate = useNavigate();
  const dateSections = useMemo(() => buildDateSections(groups), [groups]);
  const [collapsedDates, setCollapsedDates] = useState<Set<string>>(() => new Set());

  if (groups.length === 0) return null;

  const toggleDate = (key: string) => {
    setCollapsedDates((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const renderGroup = (group: TimelineCardGroup, showDateInHeader: boolean) => {
    const lead = group.cards[0];
    const symbol = lead?.company.nse_symbol || lead?.company.bse_code;
    const eventId = group.event?.event_id ?? lead?.event_id;

    return (
      <li key={group.key} className="ml-4">
        <span className="ui-dot" />
        <TimelineEventHeader
          group={group}
          showCompanyInHeader={showCompanyInHeader}
          showDateInHeader={showDateInHeader}
          onNavigate={() => {
            if (symbol && eventId) navigate(`/company/${symbol}/event/${eventId}`);
          }}
        />
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
        const expanded = !collapsedDates.has(section.key);
        const eventCount = section.groups.length;

        return (
          <section key={section.key}>
            <button
              type="button"
              onClick={() => toggleDate(section.key)}
              aria-expanded={expanded}
              className="flex w-full items-center gap-2 rounded-lg -mx-1 px-1 py-1.5 text-left hover:bg-surface-2/50 transition-colors"
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
                {section.label}
              </span>
              <span className="ml-auto text-[11px] text-ink-soft tabular-nums">
                {eventCount} {eventCount === 1 ? "event" : "events"}
              </span>
            </button>

            {expanded && (
              <ol className="relative border-l border-line ml-2 space-y-6 mt-3">
                {section.groups.map((group) => renderGroup(group, false))}
              </ol>
            )}
          </section>
        );
      })}
    </div>
  );
}
