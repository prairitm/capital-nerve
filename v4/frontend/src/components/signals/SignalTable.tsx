import { Fragment, useMemo, type KeyboardEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import type { Company, Signal } from "@/api/types";
import {
  ColumnHeaderFilter,
  CompactFilterSelect,
} from "@/components/common/ColumnHeaderFilter";
import { SeverityBadge } from "@/components/common/SeverityBadge";
import { SignalBadge } from "@/components/common/SignalBadge";
import { Pagination, usePagination } from "@/components/common/Pagination";
import { CompactSignalRow } from "@/components/signals/CompactSignalRow";
import { buildCompanyFeedGroups, type FeedTimelineEvent } from "@/lib/events";
import { eventTypeLabel, formatDate, resolveEventDisplayTitle } from "@/lib/format";
import {
  SIGNAL_CATEGORY_FILTERS,
  SIGNAL_DIRECTION_FILTERS,
  SIGNAL_SEVERITY_FILTERS,
  signalFiltersActive,
  type SignalTableFilters,
} from "@/lib/signalFilters";
import { signalCategoryLabel } from "@/lib/signals";

interface Props {
  signals: Signal[];
  title?: string;
  showCompany?: boolean;
  showSeverity?: boolean;
  filters?: SignalTableFilters;
  groupByDocumentType?: boolean;
}

interface GroupedDocumentEvent {
  company: Company;
  quarterKey: string;
  quarterLabel: string;
  quarterPeriodEndDate: string;
  event: FeedTimelineEvent;
}

function groupedDocumentEvents(signals: Signal[]): GroupedDocumentEvent[] {
  return buildCompanyFeedGroups(signals).flatMap((companyGroup) =>
    companyGroup.quarterGroups.flatMap((quarter) =>
      quarter.events.map((event) => ({
        company: companyGroup.company,
        quarterKey: quarter.key,
        quarterLabel: quarter.label,
        quarterPeriodEndDate: quarter.periodEndDate,
        event,
      })),
    ),
  );
}

function groupedPageSections(rows: GroupedDocumentEvent[]) {
  const sections = new Map<string, { key: string; label: string; rows: GroupedDocumentEvent[] }>();

  for (const row of rows) {
    const key = `${row.company.id}:${row.quarterKey}`;
    const companyLabel = row.company.ticker
      ? `${row.company.name ?? row.company.ticker} · ${row.company.ticker}`
      : row.company.name;
    const label = companyLabel ? `${companyLabel} · ${row.quarterLabel}` : row.quarterLabel;
    const section = sections.get(key) ?? { key, label, rows: [] };
    section.rows.push(row);
    sections.set(key, section);
  }

  return [...sections.values()];
}

export function SignalTable({
  signals,
  title,
  showCompany = false,
  showSeverity = false,
  filters,
  groupByDocumentType = false,
}: Props) {
  const navigate = useNavigate();
  const hasFilters = Boolean(filters);
  const activeFilters = filters ? signalFiltersActive(filters) : false;
  const groupedEvents = useMemo(() => groupedDocumentEvents(signals), [signals]);
  const pagination = usePagination(
    signals,
    10,
    filters ? `${filters.category}|${filters.direction}|${filters.severity}` : signals.length,
  );
  const groupedPagination = usePagination(
    groupedEvents,
    10,
    filters
      ? `${filters.category}|${filters.direction}|${filters.severity}|grouped`
      : `${groupedEvents.length}|grouped`,
  );
  const visibleSignals = pagination.pageItems;
  const groupedSections = useMemo(
    () => groupedPageSections(groupedPagination.pageItems),
    [groupedPagination.pageItems],
  );
  const shouldGroupByDocument = groupByDocumentType && groupedEvents.length > 0;

  if (!hasFilters && signals.length === 0) return null;

  const colSpan = 4 + (showCompany ? 1 : 0) + (showSeverity ? 1 : 0);
  const groupedColSpan = 5 + (showCompany ? 1 : 0) + (showSeverity ? 1 : 0);
  const navigateToEvent = (row: GroupedDocumentEvent) => {
    const ticker = row.company.ticker;
    if (ticker) navigate(`/company/${ticker}/event/${row.event.id}`);
  };
  const eventKeyDown = (event: KeyboardEvent, row: GroupedDocumentEvent) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      navigateToEvent(row);
    }
  };

  return (
    <section className="card overflow-hidden">
      {title && (
        <div className="px-5 py-4 border-b border-line/60">
          <h2 className="text-base font-semibold">{title}</h2>
        </div>
      )}

      {filters && activeFilters && (
        <div className="px-4 md:px-5 py-2.5 border-b border-line/40 flex flex-wrap items-center justify-between gap-3 text-xs">
          <div className="flex flex-wrap items-center gap-2 text-ink-mute">
          <span>
            {signals.length} {signals.length === 1 ? "result" : "results"}
          </span>
          {filters.category && <span className="chip-neutral">{signalCategoryLabel(filters.category)}</span>}
          {filters.severity && <span className="chip-neutral">{filters.severity.toLowerCase()} materiality</span>}
          {filters.direction && <span className="chip-neutral">{filters.direction.toLowerCase()}</span>}
          </div>
          <button
            type="button"
            onClick={filters.onClear}
            className="text-ink-mute hover:text-ink transition-colors shrink-0"
          >
            Clear filters
          </button>
        </div>
      )}

      {filters && (
        <div className="px-5 py-3 border-b border-line/40 flex flex-wrap gap-2 sm:hidden">
          <CompactFilterSelect
            label="Category"
            value={filters.category}
            options={SIGNAL_CATEGORY_FILTERS}
            onChange={filters.onCategoryChange}
          />
          <CompactFilterSelect
            label="Direction"
            value={filters.direction}
            options={SIGNAL_DIRECTION_FILTERS}
            onChange={filters.onDirectionChange}
          />
          {showSeverity && (
            <CompactFilterSelect
              label="Materiality"
              value={filters.severity}
              options={SIGNAL_SEVERITY_FILTERS}
              onChange={filters.onSeverityChange}
            />
          )}
        </div>
      )}

      {shouldGroupByDocument ? (
        <>
          <div className="md:hidden divide-y divide-line/40">
            {signals.length === 0 ? (
              <div className="px-5 py-10 text-center text-sm text-ink-mute">
                No signals match these filters.
              </div>
            ) : (
              groupedSections.map((section) => (
                <Fragment key={section.key}>
                  <div className="px-5 py-2 text-xs font-semibold uppercase tracking-wider text-ink bg-surface-2/50">
                    {section.label}
                  </div>
                  {section.rows.map((row) => {
                    const displayTitle = resolveEventDisplayTitle(row.event.event_type, row.event.title);

                    return (
                      <div key={row.event.id} className="border-t border-line/40 first:border-t-0">
                        <button
                          type="button"
                          onClick={() => navigateToEvent(row)}
                          className="w-full px-5 py-3 text-left hover:bg-surface-2/40 transition-colors"
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <div className="font-medium text-ink leading-snug">{displayTitle}</div>
                              <div className="text-xs text-ink-mute mt-1">
                                {eventTypeLabel(row.event.event_type)}
                                <span className="mx-1.5 text-ink-soft/60">·</span>
                                {formatDate(row.event.event_date)}
                              </div>
                            </div>
                            <span className="text-xs text-ink-soft shrink-0 tabular-nums">
                              {row.event.signals.length}
                            </span>
                          </div>
                        </button>
                        <div className="divide-y divide-line/30 border-t border-line/30">
                          {row.event.signals.map((signal) => (
                            <CompactSignalRow key={signal.id} signal={signal} />
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </Fragment>
              ))
            )}
          </div>

          <div className="hidden md:block overflow-x-auto">
            <table className="w-full table-fixed text-sm">
              <thead className="sticky top-0 z-10 bg-surface text-[11px] uppercase tracking-wider text-ink-soft">
                <tr>
                  {showCompany && <th className="w-44 px-5 py-2 text-left font-medium">Company</th>}
                  <th className="w-56 px-5 py-2 text-left font-medium">Document</th>
                  <th className="px-5 py-2 text-left font-medium">Signal</th>
                  {filters ? (
                    <ColumnHeaderFilter
                      label="Category"
                      value={filters.category}
                      options={SIGNAL_CATEGORY_FILTERS}
                      onChange={filters.onCategoryChange}
                      className="hidden sm:table-cell w-40"
                    />
                  ) : (
                    <th className="w-40 px-5 py-2 text-left font-medium hidden sm:table-cell">Category</th>
                  )}
                  {showSeverity &&
                    (filters ? (
                      <ColumnHeaderFilter
                        label="Materiality"
                        value={filters.severity}
                        options={SIGNAL_SEVERITY_FILTERS}
                        onChange={filters.onSeverityChange}
                        className="hidden lg:table-cell w-36"
                      />
                    ) : (
                      <th className="w-36 px-5 py-2 text-left font-medium hidden lg:table-cell">Materiality</th>
                    ))}
                  {filters ? (
                    <ColumnHeaderFilter
                      label="Direction"
                      value={filters.direction}
                      options={SIGNAL_DIRECTION_FILTERS}
                      onChange={filters.onDirectionChange}
                      className="w-32 text-right"
                    />
                  ) : (
                    <th className="w-32 px-5 py-2 text-right font-medium">Direction</th>
                  )}
                  <th className="w-8" aria-hidden />
                </tr>
              </thead>
              <tbody>
                {signals.length === 0 ? (
                  <tr>
                    <td colSpan={groupedColSpan} className="px-5 py-10 text-center text-sm text-ink-mute">
                      No signals match these filters.
                    </td>
                  </tr>
                ) : (
                  groupedSections.map((section) => (
                    <Fragment key={section.key}>
                      <tr className="bg-surface-2/50 border-t border-line/40 first:border-t-0">
                        <td
                          colSpan={groupedColSpan}
                          className="px-5 py-2 text-xs font-semibold uppercase tracking-wider text-ink"
                        >
                          {section.label}
                        </td>
                      </tr>
                      {section.rows.map((row) => {
                        const displayTitle = resolveEventDisplayTitle(row.event.event_type, row.event.title);
                        const ticker = row.company.ticker ?? null;

                        return (
                          <Fragment key={row.event.id}>
                            <tr
                              onClick={() => navigateToEvent(row)}
                              onKeyDown={(e) => eventKeyDown(e, row)}
                              tabIndex={0}
                              role="link"
                              className="border-t border-line/40 bg-surface-2/20 cursor-pointer hover:bg-surface-2/50 transition-colors group focus:outline-none focus-visible:bg-surface-2/70"
                            >
                              {showCompany && (
                                <td className="px-5 py-2.5">
                                  <div className="font-medium text-ink leading-snug">
                                    {row.company.name ?? ticker ?? "Company"}
                                  </div>
                                  {ticker && <div className="text-xs text-ink-mute mt-0.5">{ticker}</div>}
                                </td>
                              )}
                              <td className="px-5 py-2.5">
                                <div className="font-medium text-ink leading-snug">{displayTitle}</div>
                                <div className="text-xs text-ink-mute mt-0.5">
                                  {eventTypeLabel(row.event.event_type)} · {formatDate(row.event.event_date)}
                                </div>
                              </td>
                              <td className="px-5 py-2.5 text-ink-mute">
                                {row.event.signals.length} {row.event.signals.length === 1 ? "signal" : "signals"}
                              </td>
                              <td className="px-5 py-2.5 text-ink-mute hidden sm:table-cell">—</td>
                              {showSeverity && <td className="px-5 py-2.5 hidden lg:table-cell">—</td>}
                              <td className="px-5 py-2.5 text-right text-ink-soft">—</td>
                              <td className="pr-4 py-2.5 text-ink-soft group-hover:text-ink">
                                <ChevronRight
                                  size={14}
                                  className="opacity-0 group-hover:opacity-100 transition-opacity"
                                />
                              </td>
                            </tr>
                            {row.event.signals.map((signal) => {
                              const name = signal.signal_name || signal.title || signal.signal_type;
                              const category = signalCategoryLabel(signal.category);

                              return (
                                <tr
                                  key={signal.id}
                                  onClick={() => navigate(`/signals/${signal.id}`)}
                                  onKeyDown={(e) => {
                                    if (e.key === "Enter" || e.key === " ") {
                                      e.preventDefault();
                                      navigate(`/signals/${signal.id}`);
                                    }
                                  }}
                                  tabIndex={0}
                                  role="link"
                                  className="border-t border-line/30 cursor-pointer hover:bg-surface-2/30 transition-colors group focus:outline-none focus-visible:bg-surface-2/60"
                                >
                                  {showCompany && <td className="px-5 py-2.5" />}
                                  <td className="px-5 py-2.5" />
                                  <td className="px-5 py-2.5 min-w-0">
                                    <div className="font-medium text-ink leading-snug">{name}</div>
                                  </td>
                                  <td className="px-5 py-2.5 text-ink-mute hidden sm:table-cell whitespace-nowrap">
                                    {category}
                                  </td>
                                  {showSeverity && (
                                    <td className="px-5 py-2.5 hidden lg:table-cell">
                                      <SeverityBadge level={signal.severity} />
                                    </td>
                                  )}
                                  <td className="px-5 py-2.5">
                                    <div className="flex justify-end">
                                      <SignalBadge direction={signal.direction} />
                                    </div>
                                  </td>
                                  <td className="pr-4 py-2.5 text-ink-soft group-hover:text-ink">
                                    <ChevronRight
                                      size={14}
                                      className="opacity-0 group-hover:opacity-100 transition-opacity"
                                    />
                                  </td>
                                </tr>
                              );
                            })}
                          </Fragment>
                        );
                      })}
                    </Fragment>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <>
      <div className="md:hidden divide-y divide-line/40">
        {signals.length === 0 ? (
          <div className="px-5 py-10 text-center text-sm text-ink-mute">
            No signals match these filters.
          </div>
        ) : (
          visibleSignals.map((s) => {
            const name = s.signal_name || s.title || s.signal_type;
            const category = signalCategoryLabel(s.category);
            const ticker = s.company?.ticker ?? null;
            const companyName = s.company?.name ?? null;

            return (
              <div
                key={s.id}
                role="link"
                tabIndex={0}
                onClick={() => navigate(`/signals/${s.id}`)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    navigate(`/signals/${s.id}`);
                  }
                }}
                className="w-full px-5 py-3.5 text-left hover:bg-surface-2/40 transition-colors flex items-start gap-3 cursor-pointer focus:outline-none focus-visible:bg-surface-2/60"
              >
                <div className="flex-1 min-w-0">
                  {showCompany && ticker && (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        navigate(`/company/${ticker}`);
                      }}
                      className="text-xs text-ink-mute hover:text-ink transition-colors mb-1 block truncate max-w-full text-left"
                    >
                      {companyName ?? ticker}
                      <span className="text-ink-soft"> · {ticker}</span>
                    </button>
                  )}
                  <div className="font-medium text-ink leading-snug">{name}</div>
                  <div className="flex flex-wrap items-center gap-2 mt-1.5">
                    <span className="text-xs text-ink-mute">{category}</span>
                    <SignalBadge direction={s.direction} />
                    {showSeverity && <SeverityBadge level={s.severity} />}
                  </div>
                </div>
                <ChevronRight size={14} className="shrink-0 mt-1 text-ink-soft" />
              </div>
            );
          })
        )}
      </div>

      <div className="hidden md:block overflow-x-auto">
        <table className="w-full table-fixed text-sm">
          <thead className="sticky top-0 z-10 bg-surface text-[11px] uppercase tracking-wider text-ink-soft">
            <tr>
              {showCompany && (
                <th className="w-44 px-5 py-2 text-left font-medium hidden md:table-cell">Company</th>
              )}
              <th className="px-5 py-2 text-left font-medium">Signal</th>
              {filters ? (
                <ColumnHeaderFilter
                  label="Category"
                  value={filters.category}
                  options={SIGNAL_CATEGORY_FILTERS}
                  onChange={filters.onCategoryChange}
                  className="hidden sm:table-cell w-40"
                />
              ) : (
                <th className="w-40 px-5 py-2 text-left font-medium hidden sm:table-cell">Category</th>
              )}
              {showSeverity &&
                (filters ? (
                  <ColumnHeaderFilter
                    label="Materiality"
                    value={filters.severity}
                    options={SIGNAL_SEVERITY_FILTERS}
                    onChange={filters.onSeverityChange}
                    className="hidden lg:table-cell w-36"
                  />
                ) : (
                  <th className="w-36 px-5 py-2 text-left font-medium hidden lg:table-cell">Materiality</th>
                ))}
              {filters ? (
                <ColumnHeaderFilter
                  label="Direction"
                  value={filters.direction}
                  options={SIGNAL_DIRECTION_FILTERS}
                  onChange={filters.onDirectionChange}
                  className="w-32 text-right"
                />
              ) : (
                <th className="w-32 px-5 py-2 text-right font-medium">Direction</th>
              )}
              <th className="w-8" aria-hidden />
            </tr>
          </thead>
          <tbody>
            {signals.length === 0 ? (
              <tr>
                <td colSpan={colSpan} className="px-5 py-10 text-center text-sm text-ink-mute">
                  No signals match these filters.
                </td>
              </tr>
            ) : (
              visibleSignals.map((s) => {
                const name = s.signal_name || s.title || s.signal_type;
                const category = signalCategoryLabel(s.category);
                const ticker = s.company?.ticker ?? null;
                const companyName = s.company?.name ?? null;

                return (
                  <tr
                    key={s.id}
                    onClick={() => navigate(`/signals/${s.id}`)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        navigate(`/signals/${s.id}`);
                      }
                    }}
                    tabIndex={0}
                    role="link"
                    className="border-t border-line/40 cursor-pointer hover:bg-surface-2/40 transition-colors group focus:outline-none focus-visible:bg-surface-2/60"
                  >
                    {showCompany && (
                      <td className="px-5 py-2.5 hidden md:table-cell">
                        {ticker ? (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              navigate(`/company/${ticker}`);
                            }}
                            className="text-left hover:text-ink transition-colors"
                          >
                            <div className="font-medium text-ink leading-snug">
                              {companyName ?? ticker}
                            </div>
                            <div className="text-xs text-ink-mute mt-0.5">{ticker}</div>
                          </button>
                        ) : (
                          <span className="text-ink-mute">—</span>
                        )}
                      </td>
                    )}
                    <td className="px-5 py-2.5 min-w-0">
                      <div className="font-medium text-ink leading-snug">{name}</div>
                    </td>
                    <td className="px-5 py-2.5 text-ink-mute hidden sm:table-cell whitespace-nowrap">
                      {category}
                    </td>
                    {showSeverity && (
                      <td className="px-5 py-2.5 hidden lg:table-cell">
                        <SeverityBadge level={s.severity} />
                      </td>
                    )}
                    <td className="px-5 py-2.5">
                      <div className="flex justify-end">
                        <SignalBadge direction={s.direction} />
                      </div>
                    </td>
                    <td className="pr-4 py-2.5 text-ink-soft group-hover:text-ink">
                      <ChevronRight
                        size={14}
                        className="opacity-0 group-hover:opacity-100 transition-opacity"
                      />
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
        </>
      )}
      <Pagination
        page={shouldGroupByDocument ? groupedPagination.page : pagination.page}
        pageCount={shouldGroupByDocument ? groupedPagination.pageCount : pagination.pageCount}
        pageStart={shouldGroupByDocument ? groupedPagination.pageStart : pagination.pageStart}
        pageEnd={shouldGroupByDocument ? groupedPagination.pageEnd : pagination.pageEnd}
        total={shouldGroupByDocument ? groupedEvents.length : signals.length}
        onPageChange={shouldGroupByDocument ? groupedPagination.setPage : pagination.setPage}
      />
    </section>
  );
}
