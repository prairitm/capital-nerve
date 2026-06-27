import { Fragment, useMemo, type KeyboardEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import clsx from "clsx";
import type { Signal } from "@/api/types";
import { Pagination, usePagination } from "@/components/common/Pagination";
import type { QuarterEventGroup, TimelineEvent } from "@/lib/events";
import { eventTypeLabel, formatDate, resolveEventDisplayTitle } from "@/lib/format";

export interface EventSignalSummary {
  total: number;
  positive: number;
  negative: number;
  mixed: number;
}

export function eventSignalSummary(signals: Signal[]): EventSignalSummary | null {
  if (signals.length === 0) return null;
  return {
    total: signals.length,
    positive: signals.filter((s) => s.direction === "POSITIVE").length,
    negative: signals.filter((s) => s.direction === "NEGATIVE").length,
    mixed: signals.filter((s) => s.direction === "MIXED").length,
  };
}

function SignalSummaryCell({ summary }: { summary: EventSignalSummary | null }) {
  if (!summary) {
    return <span className="text-ink-soft">—</span>;
  }

  const parts: string[] = [];
  if (summary.negative > 0) parts.push(`${summary.negative}↓`);
  if (summary.positive > 0) parts.push(`${summary.positive}↑`);
  if (summary.mixed > 0) parts.push(`${summary.mixed} mixed`);

  return (
    <span className="text-ink-mute">
      <span className="text-ink font-medium num">{summary.total}</span>
      {parts.length > 0 && (
        <span className="text-ink-soft">
          {" "}
          · {parts.join(" ")}
        </span>
      )}
    </span>
  );
}

interface Props {
  quarterGroups: QuarterEventGroup<TimelineEvent>[];
  signals: Signal[];
  ticker: string;
  latestEventId?: string | null;
}

export function CompanyEventsTable({
  quarterGroups,
  signals,
  ticker,
  latestEventId = null,
}: Props) {
  const navigate = useNavigate();

  const signalsByEvent = useMemo(() => {
    const map = new Map<string, Signal[]>();
    for (const signal of signals) {
      if (!signal.event_id) continue;
      const list = map.get(signal.event_id) ?? [];
      list.push(signal);
      map.set(signal.event_id, list);
    }
    return map;
  }, [signals]);
  const eventRows = useMemo(
    () =>
      quarterGroups.flatMap((quarter) =>
        quarter.events.map((event) => ({
          event,
          quarterKey: quarter.key,
          quarterLabel: quarter.label,
          quarterPeriodEndDate: quarter.periodEndDate,
        })),
      ),
    [quarterGroups],
  );
  const pagination = usePagination(eventRows, 10, ticker);
  const visibleQuarterGroups = useMemo(() => {
    const map = new Map<string, QuarterEventGroup<TimelineEvent>>();

    for (const row of pagination.pageItems) {
      const group = map.get(row.quarterKey) ?? {
        key: row.quarterKey,
        label: row.quarterLabel,
        periodEndDate: row.quarterPeriodEndDate,
        events: [],
      };
      group.events.push(row.event);
      map.set(row.quarterKey, group);
    }

    return [...map.values()];
  }, [pagination.pageItems]);

  if (quarterGroups.length === 0) return null;

  const renderQuarterHeader = (label: string) => (
    <div
      key={label}
      className="px-5 py-2 text-xs font-semibold uppercase tracking-wider text-ink bg-surface-2/50 border-t border-line/40 first:border-t-0"
    >
      {label}
    </div>
  );

  const renderEventRow = (
    event: TimelineEvent,
    summary: EventSignalSummary | null,
    displayTitle: string,
    isLatest: boolean,
    mobile = false,
  ) => {
    const rowClass = clsx(
      mobile
        ? "w-full px-5 py-3.5 text-left hover:bg-surface-2/40 transition-colors flex items-start gap-3 cursor-pointer focus:outline-none focus-visible:bg-surface-2/60"
        : "border-t border-line/40 cursor-pointer hover:bg-surface-2/40 transition-colors group focus:outline-none focus-visible:bg-surface-2/60",
      isLatest && "bg-surface-2/20",
    );
    const navigateToEvent = () => navigate(`/company/${ticker}/event/${event.id}`);
    const rowProps = {
      onClick: navigateToEvent,
      onKeyDown: (e: KeyboardEvent) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          navigateToEvent();
        }
      },
      tabIndex: 0 as const,
      role: "link" as const,
    };

    if (mobile) {
      return (
        <div key={event.id} className={rowClass} {...rowProps}>
          <div className="flex-1 min-w-0">
            <div className="font-medium text-ink leading-snug">{displayTitle}</div>
            <div className="text-xs text-ink-mute mt-1">
              {formatDate(event.event_date)} · {eventTypeLabel(event.event_type)}
            </div>
          </div>
          <div className="shrink-0 flex flex-col items-end gap-1 pt-0.5">
            <SignalSummaryCell summary={summary} />
            <ChevronRight size={14} className="text-ink-soft" />
          </div>
        </div>
      );
    }

    return (
      <tr key={event.id} className={rowClass} {...rowProps}>
        <td className="px-5 py-2.5 text-ink-mute whitespace-nowrap">
          {formatDate(event.event_date)}
        </td>
        <td className="px-5 py-2.5">
          <div className="font-medium text-ink leading-snug">{displayTitle}</div>
          <div className="text-xs text-ink-mute mt-0.5">{eventTypeLabel(event.event_type)}</div>
        </td>
        <td className="px-5 py-2.5 text-right whitespace-nowrap">
          <SignalSummaryCell summary={summary} />
        </td>
        <td className="pr-4 py-2.5 text-ink-soft group-hover:text-ink">
          <ChevronRight
            size={14}
            className="opacity-0 group-hover:opacity-100 transition-opacity"
          />
        </td>
      </tr>
    );
  };

  return (
    <section className="card overflow-hidden">
      <div className="md:hidden divide-y divide-line/40">
        {visibleQuarterGroups.map((quarter) => (
          <Fragment key={quarter.key}>
            {renderQuarterHeader(quarter.label)}
            {quarter.events.map((event) => {
              const eventSignals = signalsByEvent.get(event.id) ?? [];
              const summary = eventSignalSummary(eventSignals);
              const displayTitle = resolveEventDisplayTitle(event.event_type, event.title);
              const isLatest = event.id === latestEventId;
              return renderEventRow(event, summary, displayTitle, isLatest, true);
            })}
          </Fragment>
        ))}
      </div>

      <div className="hidden md:block overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-[11px] uppercase tracking-wider text-ink-soft">
            <tr>
              <th className="px-5 py-2 text-left font-medium">Date</th>
              <th className="px-5 py-2 text-left font-medium">Event</th>
              <th className="px-5 py-2 text-right font-medium">Signals</th>
              <th className="w-8" aria-hidden />
            </tr>
          </thead>
          <tbody>
            {visibleQuarterGroups.map((quarter) => (
              <Fragment key={quarter.key}>
                <tr className="bg-surface-2/50 border-t border-line/40 first:border-t-0">
                  <td colSpan={4} className="px-5 py-2 text-xs font-semibold uppercase tracking-wider text-ink">
                    {quarter.label}
                  </td>
                </tr>
                {quarter.events.map((event) => {
                  const eventSignals = signalsByEvent.get(event.id) ?? [];
                  const summary = eventSignalSummary(eventSignals);
                  const displayTitle = resolveEventDisplayTitle(event.event_type, event.title);
                  const isLatest = event.id === latestEventId;

                  return renderEventRow(event, summary, displayTitle, isLatest);
                })}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
      <Pagination
        page={pagination.page}
        pageCount={pagination.pageCount}
        pageStart={pagination.pageStart}
        pageEnd={pagination.pageEnd}
        total={eventRows.length}
        onPageChange={pagination.setPage}
      />
    </section>
  );
}
