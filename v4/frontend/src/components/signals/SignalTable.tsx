import { useNavigate } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import type { MetricValue, Signal } from "@/api/types";
import {
  ColumnHeaderFilter,
  CompactFilterSelect,
} from "@/components/common/ColumnHeaderFilter";
import { SeverityBadge } from "@/components/common/SeverityBadge";
import { SignalBadge } from "@/components/common/SignalBadge";
import { Pagination, usePagination } from "@/components/common/Pagination";
import {
  SIGNAL_CATEGORY_FILTERS,
  SIGNAL_DIRECTION_FILTERS,
  SIGNAL_SEVERITY_FILTERS,
  signalFiltersActive,
  type SignalTableFilters,
} from "@/lib/signalFilters";
import { signalCategoryLabel, primaryTriggerValue } from "@/lib/signals";

interface Props {
  signals: Signal[];
  metrics?: MetricValue[];
  title?: string;
  showCompany?: boolean;
  showSeverity?: boolean;
  filters?: SignalTableFilters;
}

export function SignalTable({
  signals,
  metrics = [],
  title,
  showCompany = false,
  showSeverity = false,
  filters,
}: Props) {
  const navigate = useNavigate();
  const hasFilters = Boolean(filters);
  const activeFilters = filters ? signalFiltersActive(filters) : false;
  const pagination = usePagination(
    signals,
    10,
    filters ? `${filters.category}|${filters.direction}|${filters.severity}` : signals.length,
  );
  const visibleSignals = pagination.pageItems;

  if (!hasFilters && signals.length === 0) return null;

  const colSpan =
    5 + (showCompany ? 1 : 0) + (showSeverity ? 1 : 0);

  return (
    <section className="card overflow-hidden">
      {title && (
        <div className="px-5 py-4 border-b border-line/60">
          <h2 className="text-base font-semibold">{title}</h2>
        </div>
      )}

      {filters && activeFilters && (
        <div className="px-5 py-2 border-b border-line/40 flex items-center justify-between gap-3 text-xs">
          <span className="text-ink-mute">
            {signals.length} {signals.length === 1 ? "result" : "results"}
          </span>
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

      <div className="md:hidden divide-y divide-line/40">
        {signals.length === 0 ? (
          <div className="px-5 py-10 text-center text-sm text-ink-mute">
            No signals match these filters.
          </div>
        ) : (
          visibleSignals.map((s) => {
            const name = s.signal_name || s.title || s.signal_type;
            const category = signalCategoryLabel(s.category);
            const value = primaryTriggerValue(s, metrics);
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
                <div className="shrink-0 flex flex-col items-end gap-1 pt-0.5">
                  <span className="num text-sm font-medium text-ink whitespace-nowrap">
                    {value ?? "—"}
                  </span>
                  <ChevronRight size={14} className="text-ink-soft" />
                </div>
              </div>
            );
          })
        )}
      </div>

      <div className="hidden md:block overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-[11px] uppercase tracking-wider text-ink-soft">
            <tr>
              {showCompany && (
                <th className="px-5 py-2 text-left font-medium hidden md:table-cell">Company</th>
              )}
              <th className="px-5 py-2 text-left font-medium">Signal</th>
              {filters ? (
                <ColumnHeaderFilter
                  label="Category"
                  value={filters.category}
                  options={SIGNAL_CATEGORY_FILTERS}
                  onChange={filters.onCategoryChange}
                  className="hidden sm:table-cell"
                />
              ) : (
                <th className="px-5 py-2 text-left font-medium hidden sm:table-cell">Category</th>
              )}
              {filters ? (
                <ColumnHeaderFilter
                  label="Direction"
                  value={filters.direction}
                  options={SIGNAL_DIRECTION_FILTERS}
                  onChange={filters.onDirectionChange}
                />
              ) : (
                <th className="px-5 py-2 text-left font-medium">Direction</th>
              )}
              {showSeverity &&
                (filters ? (
                  <ColumnHeaderFilter
                    label="Materiality"
                    value={filters.severity}
                    options={SIGNAL_SEVERITY_FILTERS}
                    onChange={filters.onSeverityChange}
                    className="hidden lg:table-cell"
                  />
                ) : (
                  <th className="px-5 py-2 text-left font-medium hidden lg:table-cell">Materiality</th>
                ))}
              <th className="px-5 py-2 text-right font-medium">Value</th>
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
                const value = primaryTriggerValue(s, metrics);
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
                    <td className="px-5 py-2.5">
                      <div className="font-medium text-ink leading-snug">{name}</div>
                    </td>
                    <td className="px-5 py-2.5 text-ink-mute hidden sm:table-cell whitespace-nowrap">
                      {category}
                    </td>
                    <td className="px-5 py-2.5">
                      <SignalBadge direction={s.direction} />
                    </td>
                    {showSeverity && (
                      <td className="px-5 py-2.5 hidden lg:table-cell">
                        <SeverityBadge level={s.severity} />
                      </td>
                    )}
                    <td className="px-5 py-2.5 text-right num text-ink font-medium whitespace-nowrap">
                      {value ?? "—"}
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
      <Pagination
        page={pagination.page}
        pageCount={pagination.pageCount}
        pageStart={pagination.pageStart}
        pageEnd={pagination.pageEnd}
        total={signals.length}
        onPageChange={pagination.setPage}
      />
    </section>
  );
}
