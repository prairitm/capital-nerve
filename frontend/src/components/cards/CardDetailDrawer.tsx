import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { X, BookmarkPlus, ExternalLink, Activity, ArrowUpRight } from "lucide-react";
import clsx from "clsx";
import { api } from "@/api/client";
import type { CardMetricComparison, IntelligenceObject } from "@/api/types";
import { ConfidenceBadge } from "@/components/common/ConfidenceBadge";
import { SeverityBadge } from "@/components/common/SeverityBadge";
import { SignalBadge } from "@/components/common/SignalBadge";
import { Spinner } from "@/components/common/Spinner";
import { SourceDocumentLinks, uniqueSourceRefs } from "@/components/common/SourceDocumentLink";
import { CalculationChainPanel } from "@/components/evidence/CalculationChainPanel";
import { EvidencePanel } from "@/components/evidence/EvidencePanel";
import { MetricSparkline } from "@/components/cards/MetricSparkline";
import { cardTypeLabel, formatDate, formatNumber, formatPct, formatSigned, mainIssueLabel } from "@/lib/format";
import { useNavigate } from "react-router-dom";

interface Props {
  cardId: number | null;
  onClose: () => void;
  onSaveWatchItem?: (detail: IntelligenceObject) => void;
}

function formatMetricValue(value: number | null, unit: string): string {
  if (value === null || Number.isNaN(value)) return "—";
  if (unit === "%") return formatPct(value, 1);
  if (unit === "bps") return `${value >= 0 ? "+" : ""}${value.toFixed(0)} bps`;
  if (unit === "Cr") return `${formatNumber(value, value < 100 ? 1 : 0)} Cr`;
  return formatNumber(value, 1);
}

function formatMetricChange(row: CardMetricComparison): string | null {
  if (row.change_bps != null && row.unit === "bps") {
    return formatSigned(row.change_bps, 0, " bps");
  }
  if (row.change_bps != null) {
    return formatSigned(row.change_bps, 0, " bps");
  }
  if (row.change_percent != null) {
    return formatSigned(row.change_percent, 1, "%");
  }
  if (
    row.current_value != null &&
    row.previous_value != null &&
    row.previous_value !== 0 &&
    row.unit === "%"
  ) {
    return formatSigned(row.current_value - row.previous_value, 1, " pp");
  }
  return null;
}

function suggestedActionLabel(action: string): string {
  const map: Record<string, string> = {
    compare_with_peer_margin: "Compare with peer margin",
    check_management_commentary: "Check management commentary",
    update_model_assumptions: "Update model",
    check_operating_leverage_drivers: "Check operating leverage",
    check_segment_mix: "Check segment mix",
    compare_with_peer_growth: "Compare with peer growth",
    compare_cfo_vs_pat: "Compare CFO vs PAT",
    inspect_other_income_share: "Inspect other income share",
    review_working_capital: "Review working capital",
    inspect_cost_breakdown: "Inspect cost breakdown",
    compare_with_peer_cost_ratios: "Compare cost ratios",
    escalate_to_risk_team: "Escalate to risk team",
    review_evidence: "Review evidence",
    check_auditor_notes: "Check auditor notes",
    track_management_commentary: "Track commentary",
    review_concall_transcript: "Review concall",
    compare_with_prior_calls: "Compare with prior calls",
    review_analyst_questions: "Review analyst questions",
    monitor_topic_recurrence: "Monitor topic recurrence",
    check_interest_coverage: "Check interest coverage",
    monitor_debt_movement: "Monitor debt",
    review_segment_drivers: "Review segment drivers",
    compare_with_peer_segments: "Compare peer segments",
    open_event_detail: "Open event detail",
    review_metric_comparisons: "Review metrics",
    flag_for_review: "Flag for review",
  };
  return map[action] || action.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function timeHorizonLabel(horizon: string): string {
  switch (horizon) {
    case "short_term":
      return "Short term";
    case "medium_term":
      return "Medium term";
    case "long_term":
      return "Long term";
    default:
      return horizon.replace(/_/g, " ");
  }
}

function ImportanceBadge({ score }: { score: number }) {
  const tone =
    score >= 80 ? "text-positive" : score >= 60 ? "text-ink" : "text-ink-mute";
  return (
    <span
      className={clsx("chip-low num", tone)}
      title="Importance score (0–100) — financial materiality + severity + surprise + confidence + relevance."
    >
      <Activity size={11} className="opacity-70" />
      {score}
    </span>
  );
}

function CardSummarySection({ data }: { data: IntelligenceObject }) {
  const sourceRefs = uniqueSourceRefs(
    data.evidence,
    data.document_id ? { documentId: data.document_id, label: data.source_label } : null,
  );

  if (!data.subtitle && sourceRefs.length === 0) return null;

  return (
    <div className="card-2 p-4 space-y-3">
      {data.subtitle && (
        <div>
          <h3 className="text-xs uppercase tracking-wider text-ink-soft mb-2">Summary</h3>
          <p className="text-sm text-ink leading-relaxed">{data.subtitle}</p>
        </div>
      )}
      {sourceRefs.length > 0 && (
        <SourceDocumentLinks
          refs={sourceRefs}
          className={clsx("text-sm", data.subtitle && "pt-3 border-t border-line/50")}
        />
      )}
    </div>
  );
}

function CardVerdictChips({ data }: { data: IntelligenceObject }) {
  const hasAny =
    data.status ||
    data.severity ||
    data.confidence_score != null ||
    data.confidence;

  if (!hasAny) return null;

  return (
    <div className="flex flex-wrap items-center gap-2">
      <SignalBadge direction={data.status} />
      <SeverityBadge level={data.severity} />
      <ConfidenceBadge score={data.confidence_score} level={data.confidence} />
      <ImportanceBadge score={data.importance_score} />
    </div>
  );
}

function DisplayConfigCallout({ data }: { data: IntelligenceObject }) {
  const { display, time_horizon, investor_relevance } = data;
  if (!display.primary_metric && !display.cta && investor_relevance.length === 0) {
    return null;
  }
  return (
    <div className="card-2 p-4 space-y-3">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-xs uppercase tracking-wider text-ink-soft">Intelligence object</h3>
        <span className="text-[11px] text-ink-soft">{timeHorizonLabel(time_horizon)}</span>
      </div>
      {display.primary_metric && (
        <div>
          <div className="text-[11px] text-ink-soft uppercase tracking-wider">Primary metric</div>
          <div className="text-2xl font-semibold num text-ink leading-tight">
            {display.primary_metric}
          </div>
        </div>
      )}
      {display.cta && (
        <div className="text-xs text-ink-mute">
          <span className="text-ink-soft">Recommended action: </span>
          {display.cta}
        </div>
      )}
      {investor_relevance.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {investor_relevance.map((tag) => (
            <span key={tag} className="chip-low capitalize text-[11px]">
              {tag.replace(/_/g, " ")}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function SuggestedActions({ actions }: { actions: string[] }) {
  if (actions.length === 0) return null;
  return (
    <section>
      <h3 className="text-xs uppercase tracking-wider text-ink-soft mb-2">Suggested actions</h3>
      <div className="flex flex-wrap gap-1.5">
        {actions.map((a) => (
          <span key={a} className="chip-neutral text-[11px]">
            <ArrowUpRight size={11} />
            {suggestedActionLabel(a)}
          </span>
        ))}
      </div>
    </section>
  );
}

function CalculationPanel({ calculation }: { calculation: Record<string, unknown> }) {
  const entries = Object.entries(calculation || {}).filter(([, value]) => value !== null && value !== "");
  if (entries.length === 0) return null;

  return (
    <section className="card-2 p-4">
      <h3 className="text-xs uppercase tracking-wider text-ink-soft mb-3">Calculation</h3>
      <dl className="space-y-1.5 text-xs">
        {entries.map(([key, value]) => (
          <div key={key} className="flex items-baseline justify-between gap-3">
            <dt className="text-ink-soft capitalize">{key.replace(/_/g, " ")}</dt>
            <dd className="text-ink num text-right">
              {typeof value === "object" ? JSON.stringify(value) : String(value)}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

export function CardDetailDrawer({ cardId, onClose, onSaveWatchItem }: Props) {
  const navigate = useNavigate();
  const open = cardId !== null;

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, onClose]);

  const { data, isLoading } = useQuery({
    queryKey: ["intelligenceObject", cardId],
    queryFn: () => api<IntelligenceObject>(`/v1/intelligence-objects/${cardId}`),
    enabled: open,
  });

  if (!open) return null;

  const companySymbol = data?.company.nse_symbol || data?.company.bse_code;

  const openCompany = () => {
    if (!companySymbol) return;
    onClose();
    navigate(`/company/${companySymbol}`);
  };

  const eventId = data?.event?.event_id ?? null;
  const eventDate = data?.event?.event_date ?? null;
  const eventTitle = data?.event?.event_title ?? null;

  return (
    <div className="fixed inset-0 z-50 flex" role="dialog" aria-modal>
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <aside
        className="
          relative ml-auto bg-bg border-l border-line shadow-2xl
          w-full md:w-[560px] lg:w-[620px]
          h-full overflow-y-auto
          animate-in slide-in-from-right
        "
      >
        <header className="sticky top-0 bg-bg/95 backdrop-blur z-10 border-b border-line/70 px-5 py-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1 space-y-3">
              {data && (
                <div className="min-w-0 space-y-1">
                  {companySymbol ? (
                    <button
                      type="button"
                      onClick={openCompany}
                      className="block text-base md:text-lg font-semibold leading-snug text-ink hover:text-ink-mute truncate max-w-full text-left"
                    >
                      {data.company.short_name || data.company.company_name}
                    </button>
                  ) : (
                    <span className="block text-base md:text-lg font-semibold leading-snug text-ink truncate">
                      {data.company.short_name || data.company.company_name}
                    </span>
                  )}
                  {(companySymbol || data.period || eventDate) && (
                    <div className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-xs text-ink-mute">
                      {companySymbol && <span className="shrink-0">{companySymbol}</span>}
                      {data.period && (
                        <>
                          {companySymbol && <span className="text-line shrink-0">·</span>}
                          <span className="shrink-0">{data.period.display_label}</span>
                        </>
                      )}
                      {eventDate && (
                        <>
                          {(companySymbol || data.period) && (
                            <span className="text-line shrink-0">·</span>
                          )}
                          <span className="shrink-0">{formatDate(eventDate)}</span>
                        </>
                      )}
                    </div>
                  )}
                </div>
              )}
              <div className="text-[11px] uppercase tracking-wider text-ink-soft">
                {data ? cardTypeLabel(data.object_type) : "Intelligence object"}
              </div>
              {data && (
                <div className="space-y-2.5 min-w-0">
                  <h2 className="text-base md:text-lg font-semibold leading-snug">{data.title}</h2>
                  <CardVerdictChips data={data} />
                  <div className="flex flex-wrap gap-2 pt-0.5">
                    <button
                      type="button"
                      onClick={() => {
                        onClose();
                        navigate(`/intelligence/${data.intelligence_object_id}`);
                      }}
                      className="btn-secondary text-xs py-1.5 px-2.5"
                    >
                      Open intelligence object
                      <ExternalLink size={14} />
                    </button>
                    {eventId && companySymbol && (
                      <button
                        type="button"
                        onClick={() => {
                          onClose();
                          navigate(`/company/${companySymbol}/event/${eventId}`);
                        }}
                        className="btn-secondary text-xs py-1.5 px-2.5"
                      >
                        Open event
                        <ExternalLink size={14} />
                      </button>
                    )}
                    {onSaveWatchItem && (
                      <button
                        type="button"
                        onClick={() => onSaveWatchItem(data)}
                        className="btn-primary text-xs py-1.5 px-2.5"
                      >
                        <BookmarkPlus size={15} />
                        Save as watch item
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
            <button onClick={onClose} className="btn-ghost p-2 shrink-0" aria-label="Close">
              <X size={18} />
            </button>
          </div>
        </header>

        {isLoading || !data ? (
          <div className="p-10 flex items-center justify-center text-ink-mute gap-2">
            <Spinner /> Loading intelligence object…
          </div>
        ) : (
          <div className="p-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] space-y-5">
            <DisplayConfigCallout data={data} />
            <CardSummarySection data={data} />

            {data.insight && (
              <div className="card-2 p-4">
                <h3 className="text-xs uppercase tracking-wider text-ink-soft mb-2">Explanation</h3>
                <p className="text-sm text-ink leading-relaxed whitespace-pre-wrap">
                  {data.insight}
                </p>
              </div>
            )}

            <SuggestedActions actions={data.suggested_actions} />

            {data.metrics.length > 0 && (
              <section>
                <h3 className="text-xs uppercase tracking-wider text-ink-soft mb-2">Key metrics</h3>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                  {data.metrics.map((m, i) => (
                    <div key={i} className="card-2 p-3">
                      <div className="text-[11px] text-ink-soft mb-0.5">{m.name}</div>
                      <div className="text-base font-semibold num">
                        {typeof m.value === "number"
                          ? m.value.toLocaleString("en-IN", { maximumFractionDigits: 2 })
                          : (m.value ?? "—")}
                        {m.unit && <span className="text-ink-mute ml-1 text-xs">{m.unit}</span>}
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {data.metric_comparisons.length > 0 && (
              <section>
                <h3 className="text-xs uppercase tracking-wider text-ink-soft mb-2">
                  YoY & calculated metrics
                </h3>
                <div className="rounded-xl border border-line/60 overflow-hidden">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-surface-2/80 text-[11px] uppercase tracking-wider text-ink-soft">
                        <th className="text-left px-3 py-2 font-medium">Metric</th>
                        <th className="text-right px-3 py-2 font-medium">Current</th>
                        <th className="text-right px-3 py-2 font-medium hidden sm:table-cell">Prior</th>
                        <th className="text-right px-3 py-2 font-medium">Change</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-line/50">
                      {data.metric_comparisons.map((row) => {
                        const delta = formatMetricChange(row);
                        const deltaTone =
                          delta == null
                            ? "text-ink-mute"
                            : delta.startsWith("+")
                              ? "text-positive"
                              : delta.startsWith("-")
                                ? "text-negative"
                                : "text-ink-mute";
                        return (
                          <tr key={row.metric_code} className="bg-surface/30">
                            <td className="px-3 py-2.5 text-ink-mute text-xs">{row.metric_name}</td>
                            <td className="px-3 py-2.5 text-right font-semibold num text-ink">
                              {formatMetricValue(row.current_value, row.unit)}
                            </td>
                            <td className="px-3 py-2.5 text-right num text-ink-soft hidden sm:table-cell">
                              {formatMetricValue(row.previous_value, row.unit)}
                            </td>
                            <td className={clsx("px-3 py-2.5 text-right num text-xs font-medium", deltaTone)}>
                              {delta ?? "—"}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </section>
            )}

            <CalculationChainPanel chain={data.calculation_chain} />
            <EvidencePanel evidence={data.evidence} limit={5} />
            <CalculationPanel calculation={data.calculation} />

            {data.event_main_issue && (
              <div className="rounded-xl bg-surface-2 border border-line/60 px-4 py-3">
                <div className="text-[11px] uppercase tracking-wider text-ink-soft mb-1">
                  {mainIssueLabel(data.status)}
                </div>
                <p className="text-sm text-ink leading-relaxed">{data.event_main_issue}</p>
              </div>
            )}

            {data.watch_next && (
              <div className="rounded-xl bg-neutral-bg border border-neutral/30 px-4 py-3">
                <div className="text-[11px] uppercase tracking-wider text-neutral mb-1">Watch next</div>
                <p className="text-sm text-ink leading-relaxed">{data.watch_next}</p>
              </div>
            )}

            {data.trend_sparklines.length > 0 && (
              <section>
                <h3 className="text-xs uppercase tracking-wider text-ink-soft mb-2">
                  Quarter trend
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                  {data.trend_sparklines.map((t) => (
                    <MetricSparkline key={t.metric_code} trend={t} />
                  ))}
                </div>
              </section>
            )}

            {data.concern_heatmap.length > 0 && (
              <section className="card-2 p-4">
                <h3 className="text-xs uppercase tracking-wider text-ink-soft mb-3">
                  Analyst concern heatmap
                </h3>
                <div className="space-y-2.5">
                  {data.concern_heatmap.slice(0, 6).map((row) => (
                    <div key={row.topic}>
                      <div className="flex items-center justify-between text-xs mb-1">
                        <span className="text-ink-mute">{row.topic}</span>
                        <span className="num text-ink-soft">
                          {row.count} · {row.percent}%
                        </span>
                      </div>
                      <div className="h-1.5 rounded-full bg-surface overflow-hidden">
                        <div
                          className="h-full bg-gradient-to-r from-ink-mute to-line-strong rounded-full"
                          style={{ width: `${row.percent}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {eventTitle && (
              <div className="text-[11px] text-ink-soft">
                {eventTitle}
                {data.event_summary && (
                  <p className="mt-1 text-ink-mute line-clamp-2">{data.event_summary}</p>
                )}
              </div>
            )}
          </div>
        )}
      </aside>
    </div>
  );
}
