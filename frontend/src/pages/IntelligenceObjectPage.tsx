import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowUpRight, ChevronDown, ChevronRight } from "lucide-react";
import clsx from "clsx";
import { api } from "@/api/client";
import type {
  CardMetricComparison,
  CompanyBrief,
  EventBriefV1,
  EvidenceItem,
  IntelligenceObject,
  PeriodBrief,
} from "@/api/types";
import { MetricSparkline } from "@/components/cards/MetricSparkline";
import { SeverityBadge } from "@/components/common/SeverityBadge";
import { SignalBadge } from "@/components/common/SignalBadge";
import { PageLoader } from "@/components/common/Spinner";
import { SourceDocumentLinks, uniqueSourceRefs } from "@/components/common/SourceDocumentLink";
import {
  EvidenceInlineLinks,
  evidenceMatchingLabel,
} from "@/components/evidence/EvidenceInlineLink";
import {
  cardTypeLabel,
  formatDate,
  formatNumber,
  formatPct,
  formatSigned,
  mainIssueLabel,
} from "@/lib/format";

const ACTION_LABELS: Record<string, string> = {
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

function formatMetricValue(value: number | null, unit: string): string {
  if (value === null || Number.isNaN(value)) return "—";
  if (unit === "%") return formatPct(value, 1);
  if (unit === "bps") return `${value >= 0 ? "+" : ""}${value.toFixed(0)} bps`;
  if (unit === "Cr") return `${formatNumber(value, value < 100 ? 1 : 0)} Cr`;
  return formatNumber(value, 1);
}

function formatMetricChange(row: CardMetricComparison): string | null {
  if (row.change_bps != null) return formatSigned(row.change_bps, 0, " bps");
  if (row.change_percent != null) return formatSigned(row.change_percent, 1, "%");
  if (row.current_value != null && row.previous_value != null && row.unit === "%") {
    return formatSigned(row.current_value - row.previous_value, 1, " pp");
  }
  return null;
}

function deltaTone(delta: string | null): string {
  if (delta == null) return "text-ink-mute";
  if (delta.startsWith("+")) return "text-positive";
  if (delta.startsWith("-")) return "text-negative";
  return "text-ink-mute";
}

function ObjectMetaLinks({
  company,
  period,
  event,
  symbol,
}: {
  company: CompanyBrief;
  period: PeriodBrief | null;
  event: EventBriefV1 | null;
  symbol: string | null;
}) {
  const sep = <span className="text-ink-soft/70">·</span>;
  const companyHref = symbol ? `/company/${symbol}` : null;
  const eventHref =
    symbol && event ? `/company/${symbol}/event/${event.event_id}` : null;

  return (
    <p className="text-xs text-ink-soft mt-2 flex flex-wrap items-center gap-x-1 gap-y-0.5">
      {companyHref ? (
        <Link to={companyHref} className="ui-link font-medium">
          {company.company_name}
        </Link>
      ) : (
        <span>{company.company_name}</span>
      )}
      {period?.display_label && (
        <>
          {sep}
          {eventHref ? (
            <Link to={eventHref} className="ui-link">
              {period.display_label}
            </Link>
          ) : (
            <span>{period.display_label}</span>
          )}
        </>
      )}
      {company.sector_name && (
        <>
          {sep}
          <span>{company.sector_name}</span>
        </>
      )}
    </p>
  );
}

function normalizeText(s: string): string {
  return s.replace(/\s+/g, " ").trim().toLowerCase();
}

function subtitleDistinct(title: string, subtitle: string | null): boolean {
  if (!subtitle?.trim()) return false;
  const t = normalizeText(title);
  const s = normalizeText(subtitle);
  return s !== t && !t.includes(s) && !s.includes(t);
}

function highlightMetricCodes(data: IntelligenceObject): Set<string> {
  const codes = new Set<string>();
  for (const row of data.metric_comparisons.slice(0, 2)) {
    codes.add(row.metric_code);
  }
  return codes;
}

function ContextSection({
  data,
  symbol,
}: {
  data: IntelligenceObject;
  symbol: string | null;
}) {
  const navigate = useNavigate();
  if (!data.signal && !data.event) return null;

  return (
    <section className="card p-5 md:p-6 space-y-4">
      <h2 className="text-base font-semibold">Context</h2>

      {data.signal && (
        <div className="card-2 p-4">
          <div className="flex items-baseline justify-between gap-3">
            <div className="text-[11px] uppercase tracking-wider text-ink-soft">Signal</div>
            <button
              type="button"
              onClick={() => navigate(`/signals/${data.signal!.signal_id}`)}
              className="text-xs text-ink-soft hover:text-ink"
            >
              Open
              <ChevronRight size={14} className="inline" />
            </button>
          </div>
          <p className="text-xs text-ink-mute mt-1 capitalize">
            {data.signal.signal_category.replace(/_/g, " ")} ·{" "}
            {data.signal.signal_code.replace(/_/g, " ")}
          </p>
          {(data.signal.headline || data.signal.explanation) && (
            <p className="text-sm text-ink mt-2 line-clamp-2">
              {data.signal.headline || data.signal.explanation}
            </p>
          )}
          <div className="mt-2 flex flex-wrap gap-2">
            <SignalBadge direction={data.signal.direction} />
            <SeverityBadge level={data.signal.severity} />
          </div>
        </div>
      )}

      {data.event && (
        <div className="card-2 p-4">
          <div className="flex items-baseline justify-between gap-3">
            <div className="text-[11px] uppercase tracking-wider text-ink-soft">Event</div>
            {symbol && (
              <button
                type="button"
                onClick={() => navigate(`/company/${symbol}/event/${data.event!.event_id}`)}
                className="text-xs text-ink-soft hover:text-ink"
              >
                Open
                <ChevronRight size={14} className="inline" />
              </button>
            )}
          </div>
          <p className="text-sm font-medium text-ink mt-1">{data.event.event_title}</p>
          <p className="text-xs text-ink-mute mt-0.5">{formatDate(data.event.event_date)}</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {data.event.overall_signal && <SignalBadge direction={data.event.overall_signal} />}
            {data.event.overall_severity && <SeverityBadge level={data.event.overall_severity} />}
          </div>
        </div>
      )}

      {data.event_main_issue && (
        <div className="rounded-xl bg-surface-2 border border-line/60 p-3">
          <div className="text-[11px] uppercase tracking-wider text-ink-soft">
            {mainIssueLabel(data.status)}
          </div>
          <p className="text-sm mt-1 leading-relaxed">{data.event_main_issue}</p>
        </div>
      )}
    </section>
  );
}

export function IntelligenceObjectPage() {
  const { objectId } = useParams<{ objectId: string }>();
  const navigate = useNavigate();
  const [showCalculation, setShowCalculation] = useState(false);
  const [showDisplayConfig, setShowDisplayConfig] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["intelligenceObject", objectId],
    queryFn: () => api<IntelligenceObject>(`/v1/intelligence-objects/${objectId}`),
    enabled: !!objectId,
  });

  const sourceRefs = useMemo(
    () =>
      data
        ? uniqueSourceRefs(
            data.evidence,
            data.document_id ? { documentId: data.document_id, label: data.source_label } : null,
          )
        : [],
    [data],
  );

  const highlightCodes = useMemo(() => (data ? highlightMetricCodes(data) : new Set<string>()), [data]);

  if (isLoading) return <PageLoader />;
  if (!data) return <div className="text-ink-mute">Intelligence object not found.</div>;

  const symbol = data.company.nse_symbol || data.company.bse_code;
  const headline = data.signal?.headline?.trim() || data.title;
  const showSubtitle = subtitleDistinct(headline, data.subtitle);
  const calculationEntries = Object.entries(data.calculation || {}).filter(
    ([, v]) => v !== null && v !== "",
  );
  const hasDisplayMeta =
    Boolean(data.display.layout) ||
    Boolean(data.display.chart_type) ||
    (data.display.surfaces?.length ?? 0) > 0;

  const showWhyItMatters =
    Boolean(data.insight) ||
    Boolean(data.investor_question) ||
    Boolean(data.display.cta) ||
    data.investor_relevance.length > 0 ||
    showSubtitle;

  return (
    <div className="w-full min-w-0 space-y-5">
      <button type="button" onClick={() => navigate(-1)} className="btn-ghost -ml-2 text-sm">
        <ArrowLeft size={16} /> Back
      </button>

      {/* Verdict strip — same structure as SignalDetailPage */}
      <section className="card p-5 md:p-6">
        <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="text-[11px] uppercase tracking-wider text-ink-soft">
              {data.signal
                ? `${data.signal.signal_category.replace(/_/g, " ")} · ${data.signal.signal_code.replace(/_/g, " ")}`
                : cardTypeLabel(data.object_type)}
            </div>
            <h1 className="text-xl md:text-2xl font-semibold tracking-tight mt-1 leading-snug">
              {headline}
            </h1>

            <ObjectMetaLinks
              company={data.company}
              period={data.period ?? null}
              event={data.event}
              symbol={symbol ?? null}
            />
          </div>

          <div className="flex flex-wrap gap-2 w-full lg:w-auto shrink-0">
            {data.status && <SignalBadge direction={data.status} size="md" />}
            {data.severity && <SeverityBadge level={data.severity} size="md" />}
          </div>
        </div>
      </section>

      {showWhyItMatters && (
        <section className="card p-5 md:p-6">
          <h2 className="text-xs uppercase tracking-wider text-ink-soft mb-2">Why it matters</h2>
          {showSubtitle && (
            <p className="text-[15px] leading-relaxed text-ink-mute">{data.subtitle}</p>
          )}
          {data.insight && (
            <p
              className={clsx(
                "text-[15px] leading-relaxed text-ink whitespace-pre-wrap",
                showSubtitle && "mt-3",
              )}
            >
              {data.insight}
            </p>
          )}
          {data.investor_question && (
            <div className={clsx(data.insight && "mt-4 pt-4 border-t border-line/50")}>
              <div className="text-[11px] uppercase tracking-wider text-ink-soft mb-1">
                Investor question
              </div>
              <p className="text-sm text-ink-mute leading-relaxed">{data.investor_question}</p>
            </div>
          )}
          {data.display.cta && (
            <p className={clsx("text-sm text-ink", (data.insight || data.investor_question) && "mt-3")}>
              <span className="text-ink-soft">Recommended: </span>
              {data.display.cta}
            </p>
          )}
          {data.investor_relevance.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {data.investor_relevance.map((tag) => (
                <span key={tag} className="chip-low capitalize text-[11px]">
                  {tag.replace(/_/g, " ")}
                </span>
              ))}
            </div>
          )}
          {sourceRefs.length > 0 && <SourceDocumentLinks refs={sourceRefs} className="mt-3" />}
        </section>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
        <div className="xl:col-span-2 space-y-5 min-w-0">
          {data.metrics.length > 0 && (
            <section className="card p-5 md:p-6">
              <h2 className="text-base font-semibold mb-3">Key metrics</h2>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                {data.metrics.map((m, i) => (
                  <div key={i} className="card-2 p-3">
                    <div className="text-[11px] text-ink-soft mb-0.5 truncate">{m.name}</div>
                    <div className="text-lg font-semibold num text-ink">
                      {typeof m.value === "number"
                        ? m.unit === "%"
                          ? formatPct(m.value, 1)
                          : formatNumber(m.value, 1)
                        : (m.value ?? "—")}
                      {m.unit && m.unit !== "%" && (
                        <span className="text-ink-soft text-xs font-normal ml-0.5">{m.unit}</span>
                      )}
                      <EvidenceInlineLinks items={evidenceMatchingLabel(data.evidence, m.name)} />
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {data.metric_comparisons.length > 0 && (
            <section className="card overflow-hidden">
              <div className="px-5 py-4 border-b border-line/60">
                <h2 className="text-base font-semibold">Financial context</h2>
                <p className="text-xs text-ink-soft mt-0.5">
                  {data.period
                    ? `${data.period.display_label} vs same quarter prior year`
                    : "YoY comparisons for the latest period"}
                </p>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-[11px] uppercase tracking-wider text-ink-soft">
                    <tr>
                      <th className="px-5 py-2 text-left font-medium">Metric</th>
                      <th className="px-5 py-2 text-right font-medium">Current</th>
                      <th className="px-5 py-2 text-right font-medium hidden sm:table-cell">Prior</th>
                      <th className="px-5 py-2 text-right font-medium">Change</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.metric_comparisons.map((row) => {
                      const delta = formatMetricChange(row);
                      const highlight = highlightCodes.has(row.metric_code);
                      const rowEvidence = evidenceMatchingLabel(
                        data.evidence,
                        row.metric_code,
                        row.metric_name,
                      );
                      return (
                        <tr
                          key={row.metric_code}
                          className={clsx(
                            "border-t border-line/40",
                            highlight && "bg-surface-2/50",
                          )}
                        >
                          <td className="px-5 py-2.5 text-ink-mute">
                            {row.metric_name}
                            {highlight && (
                              <span className="ml-1.5 text-[10px] uppercase tracking-wider text-ink-soft">
                                key
                              </span>
                            )}
                          </td>
                          <td className="px-5 py-2.5 text-right num text-ink font-medium">
                            {formatMetricValue(row.current_value, row.unit)}
                            <EvidenceInlineLinks items={rowEvidence} />
                          </td>
                          <td className="px-5 py-2.5 text-right num text-ink-soft hidden sm:table-cell">
                            {formatMetricValue(row.previous_value, row.unit)}
                          </td>
                          <td
                            className={clsx(
                              "px-5 py-2.5 text-right num text-xs font-semibold",
                              deltaTone(delta),
                            )}
                          >
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

          {calculationEntries.length > 0 && (
            <section className="card overflow-hidden">
              <button
                type="button"
                onClick={() => setShowCalculation((v) => !v)}
                className="w-full flex items-center justify-between gap-3 px-5 py-4 text-left hover:bg-surface-2/40 transition-colors"
              >
                <h2 className="text-base font-semibold">How we computed this</h2>
                <ChevronDown
                  size={18}
                  className={clsx(
                    "text-ink-soft shrink-0 transition-transform",
                    showCalculation && "rotate-180",
                  )}
                />
              </button>
              {showCalculation && (
                <dl className="px-5 pb-5 space-y-1.5 text-sm border-t border-line/60">
                  {calculationEntries.map(([key, value]) => (
                    <div key={key} className="flex items-baseline justify-between gap-3">
                      <dt className="text-ink-mute capitalize">{key.replace(/_/g, " ")}</dt>
                      <dd className="text-ink num text-right break-all">
                        {typeof value === "object" ? JSON.stringify(value) : String(value)}
                      </dd>
                    </div>
                  ))}
                </dl>
              )}
            </section>
          )}

          <ContextSection data={data} symbol={symbol} />

          {(hasDisplayMeta || data.display.primary_metric) && (
            <section className="card overflow-hidden">
              <button
                type="button"
                onClick={() => setShowDisplayConfig((v) => !v)}
                className="w-full flex items-center justify-between gap-3 px-5 py-4 text-left hover:bg-surface-2/40 transition-colors"
              >
                <div>
                  <h2 className="text-base font-semibold">Display metadata</h2>
                  <p className="text-xs text-ink-soft mt-0.5">API rendering hints for downstream consumers.</p>
                </div>
                <ChevronDown
                  size={18}
                  className={clsx(
                    "text-ink-soft shrink-0 transition-transform",
                    showDisplayConfig && "rotate-180",
                  )}
                />
              </button>
              {showDisplayConfig && (
                <dl className="px-5 pb-5 grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm border-t border-line/60">
                  <div>
                    <dt className="text-[11px] uppercase tracking-wider text-ink-soft">Layout</dt>
                    <dd className="font-medium mt-0.5">{data.display.layout || "—"}</dd>
                  </div>
                  {data.display.chart_type && (
                    <div>
                      <dt className="text-[11px] uppercase tracking-wider text-ink-soft">Chart</dt>
                      <dd className="font-medium mt-0.5">{data.display.chart_type}</dd>
                    </div>
                  )}
                  {data.display.primary_metric && (
                    <div className="col-span-2">
                      <dt className="text-[11px] uppercase tracking-wider text-ink-soft">
                        Primary metric
                      </dt>
                      <dd className="font-medium num mt-0.5">{data.display.primary_metric}</dd>
                    </div>
                  )}
                  {data.display.surfaces?.length > 0 && (
                    <div className="col-span-2">
                      <dt className="text-[11px] uppercase tracking-wider text-ink-soft">Surfaces</dt>
                      <dd className="font-medium mt-0.5">{data.display.surfaces.join(", ")}</dd>
                    </div>
                  )}
                </dl>
              )}
            </section>
          )}
        </div>

        <div className="space-y-5 min-w-0">
          {data.suggested_actions.length > 0 && (
            <section className="card p-5">
              <h2 className="text-base font-semibold mb-3">Suggested actions</h2>
              <div className="flex flex-wrap gap-1.5">
                {data.suggested_actions.map((a) => (
                  <span key={a} className="chip-neutral text-[11px]">
                    <ArrowUpRight size={11} />
                    {ACTION_LABELS[a] ?? a.replace(/_/g, " ")}
                  </span>
                ))}
              </div>
            </section>
          )}

          {data.trend_sparklines.length > 0 && (
            <section className="card p-5">
              <h2 className="text-base font-semibold mb-3">Trends</h2>
              <div className="grid grid-cols-1 gap-3">
                {data.trend_sparklines.map((t) => (
                  <MetricSparkline key={t.metric_code} trend={t} />
                ))}
              </div>
            </section>
          )}

          {data.concern_heatmap.length > 0 && (
            <section className="card p-5">
              <h2 className="text-base font-semibold mb-3">Analyst concerns</h2>
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

          {data.watch_next && (
            <section className="card p-5 bg-neutral-bg border-neutral/30">
              <h2 className="text-xs uppercase tracking-wider text-neutral">Watch next</h2>
              <p className="text-sm text-ink mt-1.5 leading-relaxed">{data.watch_next}</p>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
