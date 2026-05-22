import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { BookmarkCheck, BookmarkPlus, ChevronRight, FileText } from "lucide-react";
import clsx from "clsx";
import { api } from "@/api/client";
import type { CardBrief, CompanyDetail, SignalBriefV1 } from "@/api/types";
import { IntelligenceCard } from "@/components/cards/IntelligenceCard";
import { MetricSparkline } from "@/components/cards/MetricSparkline";
import { PageLoader } from "@/components/common/Spinner";
import { SignalBadge } from "@/components/common/SignalBadge";
import { SeverityBadge } from "@/components/common/SeverityBadge";
import { filterInsightListCards, intelligenceObjectBriefToCardBrief } from "@/lib/cards";
import {
  formatCr,
  formatDate,
  formatNumber,
  formatPct,
  formatSigned,
  mainIssueLabel,
} from "@/lib/format";

const TIMELINE_INITIAL = 4;
const DOCUMENTS_INITIAL = 4;

const TONE_SURFACE: Record<string, string> = {
  positive: "bg-positive-bg border-positive/30",
  negative: "bg-negative-bg border-negative/30",
  mixed: "bg-mixed-bg border-mixed/30",
  neutral: "bg-surface-2 border-line/60",
};

/** Badge labels from the API → financial_snapshot row codes to highlight. */
const BADGE_SNAPSHOT_CODES: Record<string, string[]> = {
  Growth: ["revenue_from_operations"],
  Margins: ["ebitda_margin"],
  "Profit Quality": ["pat"],
  "Red Flags": ["pat"],
};

export function CompanyPage() {
  const { symbol } = useParams<{ symbol: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [showAllDocuments, setShowAllDocuments] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["company", symbol],
    queryFn: () => api<CompanyDetail>(`/v1/companies/${symbol}`),
    enabled: !!symbol,
  });

  const { data: companySignals = [] } = useQuery({
    queryKey: ["companySignals", symbol],
    queryFn: () => api<SignalBriefV1[]>(`/v1/companies/${symbol}/signals`, { query: { limit: 6 } }),
    enabled: !!symbol,
  });

  const toggleWatchlist = useMutation({
    mutationFn: async () => {
      if (!data) return;
      if (data.watchlist_status) {
        await api(`/watchlist/companies/${data.company.company_id}`, { method: "DELETE" });
      } else {
        await api(`/watchlist/companies`, {
          method: "POST",
          body: { company_id: data.company.company_id },
        });
      }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["company", symbol] });
      qc.invalidateQueries({ queryKey: ["watchlist"] });
    },
  });

  const highlightCodes = useMemo(() => {
    if (!data) return new Set<string>();
    const codes = new Set<string>();
    for (const b of data.badges) {
      for (const code of BADGE_SNAPSHOT_CODES[b.label] ?? []) {
        codes.add(code);
      }
    }
    return codes;
  }, [data]);

  if (isLoading) return <PageLoader />;
  if (!data) return <div className="text-ink-mute">Company not found.</div>;

  const topCards = filterInsightListCards(
    data.top_objects.map(intelligenceObjectBriefToCardBrief),
  );
  const latestEvent =
    data.latest_event_id != null
      ? data.timeline.find((e) => e.event_id === data.latest_event_id) ?? data.timeline[0]
      : data.timeline[0];
  const timelineVisible = data.timeline.slice(0, TIMELINE_INITIAL);
  const timelineLatestEventId = data.timeline[0]?.event_id ?? null;
  const documentsVisible = showAllDocuments
    ? data.documents
    : data.documents.slice(0, DOCUMENTS_INITIAL);
  const hasVerdict =
    Boolean(data.latest_summary) || Boolean(data.main_issue) || Boolean(data.watch_next) || latestEvent;

  const companySymbol =
    symbol || data.company.nse_symbol || data.company.bse_code || undefined;

  const companyMeta = [
    data.company.nse_symbol && `NSE: ${data.company.nse_symbol}`,
    data.company.bse_code && `BSE: ${data.company.bse_code}`,
    data.company.sector_name,
    data.latest_period?.display_label,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="w-full min-w-0 space-y-5">
      {/* Identity + actions */}
      <section className="card p-5 md:p-6">
        <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-xl md:text-2xl font-semibold tracking-tight truncate">
              {data.company.company_name}
            </h1>
            <div className="text-xs text-ink-soft mt-1">{companyMeta}</div>
            {(data.company.last_price != null || data.company.market_cap_cr != null) && (
              <div className="text-xs text-ink-mute mt-2 num">
                {data.company.last_price != null && (
                  <span>₹ {formatNumber(data.company.last_price, 2)}</span>
                )}
                {data.company.last_price != null && data.company.market_cap_cr != null && (
                  <span className="text-line mx-1.5">·</span>
                )}
                {data.company.market_cap_cr != null && (
                  <span>{formatCr(data.company.market_cap_cr)} mcap</span>
                )}
              </div>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2 w-full md:w-auto shrink-0">
            <button
              type="button"
              onClick={() => toggleWatchlist.mutate()}
              disabled={toggleWatchlist.isPending}
              className={clsx("btn text-xs", data.watchlist_status ? "btn-secondary" : "btn-primary")}
            >
              {data.watchlist_status ? <BookmarkCheck size={16} /> : <BookmarkPlus size={16} />}
              {data.watchlist_status ? "On watchlist" : "Add to watchlist"}
            </button>
          </div>
        </div>
      </section>

      {hasVerdict && (
        <section className="card p-5 md:p-6 space-y-5">
          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
            {data.latest_event_id && companySymbol ? (
              <button
                type="button"
                onClick={() =>
                  navigate(`/company/${companySymbol}/event/${data.latest_event_id}`)
                }
                className="min-w-0 text-left rounded-xl -ml-2 pl-2 pr-3 py-1 hover:bg-surface-2/50 transition-colors group"
              >
                <p className="text-[11px] uppercase tracking-wider text-ink-soft">
                  Latest quarterly view
                </p>
                <h2 className="text-lg md:text-xl font-semibold tracking-tight text-ink mt-1 flex items-center gap-2">
                  <span className="truncate">
                    {data.latest_period?.display_label || latestEvent?.event_title || "Latest result"}
                  </span>
                  <ChevronRight
                    size={18}
                    className="shrink-0 text-ink-soft group-hover:text-ink group-hover:translate-x-0.5 transition-all"
                  />
                </h2>
                {latestEvent?.event_date && (
                  <p className="text-xs text-ink-mute mt-1">{formatDate(latestEvent.event_date)}</p>
                )}
              </button>
            ) : (
              <div className="min-w-0">
                <p className="text-[11px] uppercase tracking-wider text-ink-soft">Latest quarterly view</p>
                <h2 className="text-lg font-semibold tracking-tight mt-1">
                  {data.latest_period?.display_label || "Latest result"}
                </h2>
              </div>
            )}
            {(latestEvent?.overall_signal || latestEvent?.overall_severity) && (
              <div className="flex flex-wrap items-center gap-2 shrink-0">
                {latestEvent.overall_signal && (
                  <SignalBadge direction={latestEvent.overall_signal} size="md" />
                )}
                {latestEvent.overall_severity && (
                  <SeverityBadge level={latestEvent.overall_severity} size="md" />
                )}
              </div>
            )}
          </div>

          {data.badges.length > 0 && (
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
              {data.badges.map((b, i) => (
                <div
                  key={i}
                  className={clsx(
                    "rounded-xl border px-3 py-2.5",
                    TONE_SURFACE[b.tone] || TONE_SURFACE.neutral,
                  )}
                >
                  <div className="text-[10px] uppercase tracking-wider text-ink-soft leading-tight">
                    {b.label}
                  </div>
                  <div className="text-sm font-semibold mt-1 leading-snug">{b.value}</div>
                </div>
              ))}
            </div>
          )}

          {data.latest_summary && (
            <p className="text-[15px] md:text-base leading-relaxed text-ink">{data.latest_summary}</p>
          )}

          {(data.main_issue || data.watch_next) && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {data.main_issue && (
                <div className="rounded-xl bg-surface-2 border border-line/60 p-3">
                  <div className="text-[11px] uppercase tracking-wider text-ink-soft">
                    {mainIssueLabel(latestEvent?.overall_signal ?? null)}
                  </div>
                  <div className="text-sm mt-1 leading-relaxed">{data.main_issue}</div>
                </div>
              )}
              {data.watch_next && (
                <div className="rounded-xl bg-neutral-bg border border-neutral/30 p-3">
                  <div className="text-[11px] uppercase tracking-wider text-neutral">Watch next</div>
                  <div className="text-sm mt-1 leading-relaxed">{data.watch_next}</div>
                </div>
              )}
            </div>
          )}
        </section>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
        <div className="xl:col-span-2 space-y-5 min-w-0">
          {data.timeline.length > 0 && (
            <section className="card p-5 md:p-6">
              <div className="flex items-baseline justify-between gap-3 mb-3">
                <h2 className="text-base font-semibold">Recent events</h2>
                {data.timeline.length > TIMELINE_INITIAL && symbol && (
                  <button
                    type="button"
                    onClick={() => navigate(`/company/${symbol}/events`)}
                    className="text-xs text-ink-soft hover:text-ink"
                  >
                    View all
                    <ChevronRight size={14} className="inline" />
                  </button>
                )}
              </div>
              <ol className="relative border-l border-line ml-2">
                {timelineVisible.map((ev) => {
                  const isLatest = ev.event_id === timelineLatestEventId;
                  return (
                    <li key={ev.event_id} className="ml-4 mb-4 last:mb-0">
                      <span className={clsx("ui-dot", isLatest && "bg-brand ring-2 ring-brand/30")} />
                      <button
                        type="button"
                        onClick={() => navigate(`/company/${symbol}/event/${ev.event_id}`)}
                        className={clsx(
                          "w-full text-left rounded-lg -mx-2 px-2 py-1 transition-colors",
                          isLatest ? "bg-surface-2/60" : "hover:bg-surface-2/40",
                        )}
                      >
                        <span className="text-[11px] uppercase tracking-wider text-ink-soft">
                          {formatDate(ev.event_date)} ·{" "}
                          {ev.event_type.replace(/_/g, " ").toLowerCase()}
                        </span>
                        <div className="font-medium mt-1">{ev.event_title}</div>
                        {(ev.overall_signal || ev.overall_severity) && (
                          <div className="flex items-center gap-2 mt-1.5">
                            {ev.overall_signal && <SignalBadge direction={ev.overall_signal} />}
                            {ev.overall_severity && <SeverityBadge level={ev.overall_severity} />}
                          </div>
                        )}
                        {ev.summary_text && (
                          <p className="text-xs text-ink-mute mt-2 line-clamp-2">{ev.summary_text}</p>
                        )}
                      </button>
                    </li>
                  );
                })}
              </ol>
            </section>
          )}

          {topCards.length > 0 && (
            <section className="card rounded-xl overflow-hidden">
              <div className="px-4 py-4 border-b border-line/60 bg-surface-2/30">
                <h2 className="text-base font-semibold">Key intelligence</h2>
                <p className="text-sm text-ink-mute mt-0.5">
                  Highest-priority cards for this company.
                </p>
              </div>
              <div className="p-4 space-y-3">
                {topCards.map((c: CardBrief) => (
                  <IntelligenceCard key={c.card_id} card={c} showCompany={false} />
                ))}
              </div>
            </section>
          )}

          {data.documents.length > 0 && (
            <section className="card p-5 md:p-6">
              <div className="flex items-baseline justify-between gap-3 mb-3">
                <h2 className="text-base font-semibold">Documents</h2>
                {data.documents.length > DOCUMENTS_INITIAL && (
                  <button
                    type="button"
                    onClick={() => setShowAllDocuments((v) => !v)}
                    className="text-xs text-ink-soft hover:text-ink shrink-0"
                  >
                    {showAllDocuments
                      ? "Show fewer"
                      : `View all ${data.documents.length} documents`}
                  </button>
                )}
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {documentsVisible.map((d) => (
                  <Link
                    key={d.document_id}
                    to={`/documents/${d.document_id}`}
                    className="card-2 p-3 hover:border-line-strong block"
                  >
                    <div className="flex items-start gap-3">
                      <FileText size={18} className="text-ink-mute mt-0.5 shrink-0" />
                      <div className="min-w-0 flex-1">
                        <div className="text-sm font-medium truncate">{d.document_title}</div>
                        <div className="text-[11px] text-ink-soft mt-0.5">
                          {d.document_type.replace(/_/g, " ").toLowerCase()} ·{" "}
                          {formatDate(d.document_date)}
                        </div>
                        <div className="text-[11px] text-ink-soft mt-1">
                          {d.values_extracted ?? 0} values · {d.cards_generated ?? 0} cards
                          {d.extraction_confidence != null &&
                            ` · ${d.extraction_confidence.toFixed(0)}% confidence`}
                        </div>
                      </div>
                    </div>
                  </Link>
                ))}
              </div>
            </section>
          )}
        </div>

        <div className="space-y-5 min-w-0">
          {companySignals.length > 0 && (
            <section className="card p-5">
              <div className="flex items-baseline justify-between gap-2 mb-3">
                <h2 className="text-base font-semibold">Signals</h2>
                <button
                  type="button"
                  onClick={() => navigate("/signals")}
                  className="text-xs text-ink-soft hover:text-ink"
                >
                  All signals
                  <ChevronRight size={14} className="inline" />
                </button>
              </div>
              <div className="divide-y divide-line/50">
                {companySignals.map((s) => (
                  <button
                    key={s.signal_id}
                    type="button"
                    onClick={() => navigate(`/signals/${s.signal_id}`)}
                    className="w-full flex items-center justify-between gap-3 py-3 first:pt-0 last:pb-0 text-left hover:bg-surface-2/40 -mx-2 px-2 rounded-lg transition-colors"
                  >
                    <div className="min-w-0">
                      <div className="text-sm font-medium line-clamp-2">
                        {s.headline || s.signal_name}
                      </div>
                      <div className="text-xs text-ink-soft mt-0.5 capitalize">
                        {s.signal_category.replace(/_/g, " ")}
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      <SignalBadge direction={s.direction} />
                      <ChevronRight size={16} className="text-ink-soft" />
                    </div>
                  </button>
                ))}
              </div>
            </section>
          )}

          {data.financial_snapshot.length > 0 && (
            <section className="card overflow-hidden">
              <div className="px-5 py-4 border-b border-line/60">
                <h2 className="text-base font-semibold">Financial snapshot</h2>
                <p className="text-xs text-ink-soft mt-0.5">
                  {data.latest_period
                    ? `${data.latest_period.display_label} vs prior year`
                    : "Latest quarter vs prior year"}
                </p>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-[11px] uppercase tracking-wider text-ink-soft">
                    <tr>
                      <th className="px-5 py-2 text-left font-medium">Metric</th>
                      <th className="px-5 py-2 text-right font-medium">Current</th>
                      <th className="px-5 py-2 text-right font-medium hidden sm:table-cell">Prior</th>
                      <th className="px-5 py-2 text-right font-medium">YoY</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.financial_snapshot.map((row) => {
                      const highlight = highlightCodes.has(row.code);
                      return (
                        <tr
                          key={row.code}
                          className={clsx(
                            "border-t border-line/40",
                            highlight && "bg-surface-2/50",
                          )}
                        >
                          <td className="px-5 py-2.5 text-ink-mute">
                            {row.metric}
                            {highlight && (
                              <span className="ml-1.5 text-[10px] uppercase tracking-wider text-ink-soft">
                                flagged
                              </span>
                            )}
                          </td>
                          <td className="px-5 py-2.5 text-right num text-ink font-medium">
                            {row.unit === "%"
                              ? formatPct(row.current_value)
                              : formatNumber(row.current_value, 1)}
                            {row.unit !== "%" && (
                              <span className="text-ink-soft text-xs ml-1">{row.unit}</span>
                            )}
                          </td>
                          <td className="px-5 py-2.5 text-right num text-ink-soft hidden sm:table-cell">
                            {row.unit === "%"
                              ? formatPct(row.previous_value)
                              : formatNumber(row.previous_value, 1)}
                          </td>
                          <td
                            className={clsx(
                              "px-5 py-2.5 text-right num text-xs font-semibold",
                              row.yoy_change_pct === null
                                ? "text-ink-mute"
                                : row.yoy_change_pct >= 0
                                  ? "text-positive"
                                  : "text-negative",
                            )}
                          >
                            {row.yoy_change_pct === null
                              ? "—"
                              : formatSigned(row.yoy_change_pct, 1, "%")}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {data.trends.length > 0 && (
            <section className="card p-5">
              <h2 className="text-base font-semibold mb-3">Trends</h2>
              <div className="grid grid-cols-1 gap-3">
                {data.trends.slice(0, 3).map((t) => (
                  <MetricSparkline key={t.metric_code} trend={t} />
                ))}
              </div>
            </section>
          )}
        </div>
      </div>

    </div>
  );
}
