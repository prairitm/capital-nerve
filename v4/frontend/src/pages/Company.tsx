import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, FileText } from "lucide-react";
import clsx from "clsx";
import { api } from "@/api/client";
import type { CompanyHub, SnapshotRow, TrendSeries } from "@/api/types";
import { QuarterSignalsTimeline } from "@/components/feed/QuarterSignalsTimeline";
import { TrendChart } from "@/components/charts/TrendChart";
import { BackButton } from "@/components/common/BackButton";
import { PageLoader } from "@/components/common/Spinner";
import { Empty } from "@/components/common/Empty";
import { ErrorState, MetricCard, PageHeader, PageSkeleton } from "@/components/common/DashboardUI";
import { Pagination, usePagination } from "@/components/common/Pagination";
import { buildCompanyFeedGroupFromHub } from "@/lib/events";
import { formatMetricValue, formatPct, resolveEventDisplayTitle } from "@/lib/format";

const TREND_CODES = ["revenue_yoy_growth", "ebitda_margin", "pat_margin"];

function FinancialSnapshotTable({ rows, periodLabel }: { rows: SnapshotRow[]; periodLabel?: string | null }) {
  const hasPriorData = rows.some((r) => r.previous_value != null);
  const pagination = usePagination(rows, 10, periodLabel);
  const visibleRows = pagination.pageItems;

  return (
    <section className="card overflow-hidden">
      <div className="px-5 py-4 border-b border-line/60">
        <h2 className="text-base font-semibold">Key numbers</h2>
        <p className="text-xs text-ink-soft mt-0.5">
          {periodLabel
            ? hasPriorData
              ? `${periodLabel} vs prior year`
              : `${periodLabel} — current quarter`
            : hasPriorData
              ? "Latest quarter vs prior year"
              : "Latest quarter"}
        </p>
      </div>
      {rows.length <= 6 ? (
        <div className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-3">
          {rows.map((row) => (
            <MetricCard key={row.code} label={row.metric} value={formatMetricValue(row.current_value, row.unit)} prior={row.previous_value != null ? formatMetricValue(row.previous_value, row.unit) : undefined} change={row.yoy_change_pct} />
          ))}
        </div>
      ) : <>
      <div className="md:hidden divide-y divide-line/40">
        {visibleRows.map((row) => {
          const positive = row.yoy_change_pct != null && row.yoy_change_pct > 0;
          const yoyLabel =
            row.yoy_change_pct == null
              ? "—"
              : `${positive ? "+" : ""}${formatPct(row.yoy_change_pct)}`;

          return (
            <div key={row.code} className="px-5 py-3 flex items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="text-ink-mute">{row.metric}</div>
                {hasPriorData && row.previous_value != null && (
                  <div className="text-xs text-ink-soft mt-1 num">
                    Prior {formatMetricValue(row.previous_value, row.unit)}
                  </div>
                )}
              </div>
              <div className="shrink-0 text-right">
                <div className="num text-ink font-medium">
                  {formatMetricValue(row.current_value, row.unit)}
                </div>
                {hasPriorData && (
                  <div
                    className={clsx(
                      "text-xs num font-medium mt-1",
                      row.yoy_change_pct == null
                        ? "text-ink-soft"
                        : positive
                          ? "text-positive"
                          : "text-negative",
                    )}
                  >
                    {yoyLabel} YoY
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
      <div className="hidden md:block overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-[11px] uppercase tracking-wider text-ink-soft">
            <tr>
              <th className="px-5 py-2 text-left font-medium">Metric</th>
              <th className="px-5 py-2 text-right font-medium">
                {hasPriorData ? "Current" : "Value"}
              </th>
              {hasPriorData && (
                <>
                  <th className="px-5 py-2 text-right font-medium">Prior</th>
                  <th className="px-5 py-2 text-right font-medium">YoY</th>
                </>
              )}
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((row) => {
              const positive = row.yoy_change_pct != null && row.yoy_change_pct > 0;
              return (
                <tr key={row.code} className="border-t border-line/40">
                  <td className="px-5 py-2.5 text-ink-mute">{row.metric}</td>
                  <td className="px-5 py-2.5 text-right num text-ink font-medium">
                    {formatMetricValue(row.current_value, row.unit)}
                  </td>
                  {hasPriorData && (
                    <>
                      <td className="px-5 py-2.5 text-right num text-ink-soft">
                        {formatMetricValue(row.previous_value, row.unit)}
                      </td>
                      <td
                        className={clsx(
                          "px-5 py-2.5 text-right num font-medium",
                          row.yoy_change_pct == null
                            ? "text-ink-soft"
                            : positive
                              ? "text-positive"
                              : "text-negative",
                        )}
                      >
                        {row.yoy_change_pct == null
                          ? "—"
                          : `${positive ? "+" : ""}${formatPct(row.yoy_change_pct)}`}
                      </td>
                    </>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <Pagination
        page={pagination.page}
        pageCount={pagination.pageCount}
        pageStart={pagination.pageStart}
        pageEnd={pagination.pageEnd}
        total={rows.length}
        onPageChange={pagination.setPage}
      />
      </>}
    </section>
  );
}

export function Company() {
  const { ticker } = useParams<{ ticker: string }>();
  const [documentsOpen, setDocumentsOpen] = useState(false);

  const companyQuery = useQuery({
    queryKey: ["company", ticker],
    queryFn: () => api<CompanyHub>(`/companies/${ticker}`),
    enabled: !!ticker,
  });
  const { data, isLoading } = companyQuery;

  const { data: trends = [] } = useQuery({
    queryKey: ["company-trends", ticker],
    queryFn: () =>
      api<TrendSeries[]>(`/companies/${ticker}/trends`, {
        query: { codes: TREND_CODES.join(",") },
      }),
    enabled: !!ticker,
  });

  const feedGroup = useMemo(() => {
    if (!data) return null;
    return buildCompanyFeedGroupFromHub(data.company, data.timeline, data.signals);
  }, [data]);

  const trendsWithData = useMemo(
    () => trends.filter((s) => s.points.filter((p) => p.value != null).length >= 2),
    [trends],
  );

  if (isLoading) return <PageSkeleton rows={4} />;
  if (companyQuery.isError) return <ErrorState title="Company unavailable" description="The company profile could not be loaded." onRetry={() => void companyQuery.refetch()} />;
  if (!data || !ticker) return <ErrorState title="Company not found" description="This company is not part of the current coverage universe." />;

  const { company, financial_snapshot, documents } = data;
  const latestEventHref = data.latest_event_id
    ? `/company/${ticker}/event/${data.latest_event_id}`
    : null;
  const latestPeriodEvents = (data.latest_period_events ?? []).filter((event) => event.document_id);

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <BackButton fallback="/companies" />

      <PageHeader eyebrow={`${company.ticker}${company.exchange ? ` · ${company.exchange}` : ""}`} title={company.name ?? company.ticker ?? "Company"} description={company.industry ?? company.sector ?? "Company intelligence and reported financial performance."} action={
        <div className="flex max-w-full flex-wrap items-center justify-end gap-2">
          {data.latest_period_label && latestEventHref && (
            <Link to={latestEventHref} className="chip-neutral hover:border-line-strong transition-colors">
              {data.latest_period_label}
            </Link>
          )}
          {latestPeriodEvents.length > 0
            ? latestPeriodEvents.map((event) => (
                <Link
                  key={event.id}
                  to={`/company/${ticker}/event/${event.id}`}
                  className="focus-ring hidden sm:inline-flex text-sm text-ink-mute hover:text-ink items-center gap-1 rounded-lg"
                >
                  <FileText size={14} />
                  {resolveEventDisplayTitle(event.event_type, event.title)}
                  <ChevronRight size={14} />
                </Link>
              ))
            : latestEventHref && (
                <Link
                  to={latestEventHref}
                  className="text-sm text-ink-mute hover:text-ink inline-flex items-center gap-1"
                >
                  View results <ChevronRight size={14} />
                </Link>
              )}
        </div>
      } />

      {financial_snapshot.length > 0 && (
        <FinancialSnapshotTable rows={financial_snapshot} periodLabel={data.latest_period_label} />
      )}

      {data.signals.length > 0 && feedGroup && feedGroup.quarterGroups.length > 0 ? (
        <section className="card overflow-hidden">
          <div className="px-5 py-4 border-b border-line/60 flex items-center justify-between gap-3">
            <h2 className="text-base font-semibold">Signals by period</h2>
            <Link
              to={`/company/${ticker}/events`}
              className="text-xs text-ink-mute hover:text-ink inline-flex items-center gap-1 shrink-0"
            >
              All events <ChevronRight size={13} />
            </Link>
          </div>
          <QuarterSignalsTimeline
            quarterGroups={feedGroup.quarterGroups}
            ticker={ticker}
            collapsible={feedGroup.quarterGroups.length > 1}
          />
        </section>
      ) : null}

      {trendsWithData.length > 0 && (
        <section className="card p-5">
          <h2 className="text-base font-semibold mb-4">Trends</h2>
          <div className="grid gap-6 sm:grid-cols-3">
            {trendsWithData.map((s) => (
              <TrendChart key={s.metric_code} series={s} />
            ))}
          </div>
        </section>
      )}

      {feedGroup && feedGroup.quarterGroups.length > 0 && data.signals.length === 0 && (
        <section className="card overflow-hidden">
          <div className="flex items-center justify-between gap-3 border-b border-line/60 px-5 py-4">
            <div><h2 className="text-base font-semibold">Reporting history</h2><p className="mt-0.5 text-xs text-ink-mute">No material signals detected in these reports.</p></div>
            <Link to={`/company/${ticker}/events`} className="ui-link text-xs">All events</Link>
          </div>
          <QuarterSignalsTimeline quarterGroups={feedGroup.quarterGroups} ticker={ticker} collapsible={feedGroup.quarterGroups.length > 1} />
        </section>
      )}

      {documents.length > 0 && (
        <section className="card overflow-hidden">
          <button
            type="button"
            onClick={() => setDocumentsOpen((v) => !v)}
            aria-expanded={documentsOpen}
            className="w-full px-5 py-4 flex items-center justify-between gap-3 text-left hover:bg-surface-2/30 transition-colors"
          >
            <h2 className="text-base font-semibold">Source documents</h2>
            <span className="inline-flex items-center gap-1.5 text-xs text-ink-mute shrink-0">
              {documents.length}
              <ChevronDown
                size={14}
                className={clsx("transition-transform", documentsOpen && "rotate-180")}
              />
            </span>
          </button>
          {documentsOpen && (
            <ul className="border-t border-line/60">
              {documents.map((d) => (
                <Link
                  key={d.id}
                  to={`/documents/${d.id}`}
                  className="flex items-center gap-3 px-5 py-3 border-t border-line/40 first:border-t-0 hover:bg-surface-2/40 transition-colors"
                >
                  <FileText size={16} className="text-ink-soft shrink-0" />
                  <span className="text-sm text-ink truncate flex-1">
                    {d.title || d.document_kind || "Document"}
                  </span>
                </Link>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}
