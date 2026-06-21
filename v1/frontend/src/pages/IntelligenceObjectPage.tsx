import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, ChevronDown } from "lucide-react";
import { BackButton } from "@/components/common/BackButton";
import clsx from "clsx";
import { api } from "@/api/client";
import type {
  CardMetricComparison,
  CompanyBrief,
  EventBriefV1,
  IntelligenceObject,
  PeriodBrief,
} from "@/api/types";
import { MetricSparkline } from "@/components/cards/MetricSparkline";
import { KeyMetricsPanel } from "@/components/cards/KeyMetricsPanel";
import { SeverityBadge } from "@/components/common/SeverityBadge";
import { SignalBadge } from "@/components/common/SignalBadge";
import { PageLoader } from "@/components/common/Spinner";
import { SourceDocumentLinks, uniqueSourceRefs } from "@/components/common/SourceDocumentLink";
import {
  CalculationChainPanel,
} from "@/components/evidence/CalculationChainPanel";
import { ReproducibilityExportButton } from "@/components/evidence/ReproducibilityExportButton";
import {
  EvidenceInlineLinks,
  evidenceMatchingLabel,
} from "@/components/evidence/EvidenceInlineLink";
import {
  cardTypeLabel,
  cleanCardSummary,
  formatMetricValue,
  formatSigned,
} from "@/lib/format";

const GENERIC_INVESTOR_QUESTIONS = new Set([
  "what is driving the change this quarter?",
]);

const GENERIC_CTAS = new Set(["open event detail", "review metrics"]);

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

function whyItMattersNarrative(data: IntelligenceObject): string | null {
  const insight = cleanCardSummary(data.insight);
  const subtitle = cleanCardSummary(data.subtitle);
  if (insight && subtitle && normalizeText(insight) === normalizeText(subtitle)) {
    return insight;
  }
  return insight || subtitle;
}

function isUsefulInvestorQuestion(question: string | null | undefined): boolean {
  if (!question?.trim()) return false;
  return !GENERIC_INVESTOR_QUESTIONS.has(question.trim().toLowerCase());
}

function isUsefulCta(cta: string | null | undefined): boolean {
  if (!cta?.trim()) return false;
  return !GENERIC_CTAS.has(cta.trim().toLowerCase());
}

function highlightMetricCodes(data: IntelligenceObject): Set<string> {
  const codes = new Set<string>();
  for (const row of data.metric_comparisons.slice(0, 2)) {
    codes.add(row.metric_code);
  }
  return codes;
}

export function IntelligenceObjectPage() {
  const { objectId } = useParams<{ objectId: string }>();
  const [showCalculation, setShowCalculation] = useState(false);

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
  const narrative = whyItMattersNarrative(data);
  const calculationEntries = Object.entries(data.calculation || {}).filter(
    ([, v]) => v !== null && v !== "",
  );

  const showWhyItMatters =
    Boolean(narrative) ||
    isUsefulInvestorQuestion(data.investor_question) ||
    isUsefulCta(data.display.cta) ||
    sourceRefs.length > 0;

  return (
    <div className="w-full min-w-0 space-y-5">
      <div className="flex items-center justify-between gap-3">
        <BackButton
          fallback={
            symbol ? `/company/${symbol}` : "/"
          }
        />
        <ReproducibilityExportButton objectId={data.intelligence_object_id} />
      </div>

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
        <section className="card p-5 md:p-6 space-y-4">
          <h2 className="text-xs uppercase tracking-wider text-ink-soft">Why it matters</h2>
          {narrative && (
            <p className="text-[15px] leading-relaxed text-ink">{narrative}</p>
          )}
          {isUsefulInvestorQuestion(data.investor_question) && (
            <div className="rounded-xl border border-line/50 bg-surface-2/30 px-4 py-3">
              <div className="text-[11px] uppercase tracking-wider text-ink-soft mb-1">
                Investor question
              </div>
              <p className="text-sm text-ink-mute leading-relaxed">{data.investor_question}</p>
            </div>
          )}
          {isUsefulCta(data.display.cta) && (
            <p className="text-sm text-ink">
              <span className="text-ink-soft">Recommended: </span>
              {data.display.cta}
            </p>
          )}
          {sourceRefs.length > 0 && <SourceDocumentLinks refs={sourceRefs} />}
        </section>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
        <div className="xl:col-span-2 space-y-5 min-w-0">
          {data.metrics.length > 0 && (
            <KeyMetricsPanel
              metrics={data.metrics}
              evidence={data.evidence}
              calculationChain={data.calculation_chain}
              subtitle={
                data.period?.display_label
                  ? `Figures for ${data.period.display_label}`
                  : "Figures from the filing"
              }
            />
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

          <CalculationChainPanel chain={data.calculation_chain} />

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
