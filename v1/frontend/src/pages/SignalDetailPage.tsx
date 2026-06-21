import { useMemo } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, Check, ChevronRight, X } from "lucide-react";
import { BackButton } from "@/components/common/BackButton";
import clsx from "clsx";
import { api } from "@/api/client";
import type {
  CardMetricComparison,
  CompanyBrief,
  EvidenceItem,
  PeriodBrief,
  SignalDetailV1,
  SignalEventBriefV1,
  SignalRuleLeafV1,
} from "@/api/types";
import { MetricSparkline } from "@/components/cards/MetricSparkline";
import { PageLoader } from "@/components/common/Spinner";
import { SeverityBadge } from "@/components/common/SeverityBadge";
import { SignalBadge } from "@/components/common/SignalBadge";
import { SourceDocumentLinks, uniqueSourceRefs } from "@/components/common/SourceDocumentLink";
import {
  EvidenceInlineLinks,
  evidenceMatchingLabel,
} from "@/components/evidence/EvidenceInlineLink";
import {
  formatDate,
  formatMetricValue,
  formatPct,
  formatSigned,
  cleanCardSummary,
  mainIssueLabel,
} from "@/lib/format";

const CATEGORY_ACTIONS: Record<string, string[]> = {
  earnings_quality: [
    "inspect_other_income_share",
    "compare_cfo_vs_pat",
    "review_metric_comparisons",
  ],
  cash_quality: ["compare_cfo_vs_pat", "review_working_capital"],
  margin: ["compare_with_peer_margin", "inspect_cost_breakdown"],
  growth: ["compare_with_peer_growth", "check_segment_mix"],
  expense: ["inspect_cost_breakdown", "compare_with_peer_cost_ratios"],
  red_flag: ["check_auditor_notes", "escalate_to_risk_team"],
  management: ["review_concall_transcript", "track_management_commentary"],
};

const ACTION_LABELS: Record<string, string> = {
  inspect_other_income_share: "Inspect other income share",
  compare_cfo_vs_pat: "Compare CFO vs PAT",
  review_metric_comparisons: "Review metric comparisons",
  review_working_capital: "Review working capital",
  compare_with_peer_margin: "Compare with peer margin",
  inspect_cost_breakdown: "Inspect cost breakdown",
  compare_with_peer_growth: "Compare with peer growth",
  check_segment_mix: "Check segment mix",
  compare_with_peer_cost_ratios: "Compare cost ratios",
  check_auditor_notes: "Check auditor notes",
  escalate_to_risk_team: "Escalate to risk team",
  review_concall_transcript: "Review concall transcript",
  track_management_commentary: "Track management commentary",
};

function companySymbol(company: CompanyBrief) {
  return company.nse_symbol || company.bse_code || null;
}

function SignalMetaLinks({
  company,
  period,
  event,
  symbol,
}: {
  company: CompanyBrief;
  period: PeriodBrief | null;
  event: SignalEventBriefV1 | null;
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

function formatMetricChange(row: CardMetricComparison): string | null {
  if (row.change_bps != null) return formatSigned(row.change_bps, 0, " bps");
  if (row.change_percent != null) return formatSigned(row.change_percent, 1, "%");
  if (
    row.current_value != null &&
    row.previous_value != null &&
    row.unit === "%"
  ) {
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

function isRuleMetric(code: string, ruleCodes: string[], triggerCode: string | undefined) {
  return ruleCodes.includes(code) || code === triggerCode;
}

function RuleLeafRow({
  leaf,
  evidence,
}: {
  leaf: SignalRuleLeafV1;
  evidence: EvidenceItem[];
}) {
  const leafEvidence = evidenceMatchingLabel(evidence, leaf.metric_code, leaf.metric_name);
  return (
    <div className="card-2 p-3 flex items-start justify-between gap-3">
      <div className="min-w-0">
        <div className="text-sm font-medium text-ink">{leaf.metric_name}</div>
        <div className="text-xl font-semibold num text-ink mt-0.5 leading-tight">
          {formatMetricValue(leaf.current_value, leaf.unit)}
          <EvidenceInlineLinks items={leafEvidence} />
        </div>
        {leaf.rule_text && (
          <p className="text-xs text-ink-soft mt-1">{leaf.rule_text}</p>
        )}
      </div>
      {leaf.passed != null && (
        <span
          className={clsx(
            "shrink-0 inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full border",
            leaf.passed
              ? "bg-positive-bg text-positive border-positive/30"
              : "bg-negative-bg text-negative border-negative/30",
          )}
        >
          {leaf.passed ? <Check size={12} /> : <X size={12} />}
          {leaf.passed ? "Met" : "Not met"}
        </span>
      )}
    </div>
  );
}

function isRenderableRuleLeaf(leaf: SignalRuleLeafV1): boolean {
  return Boolean(leaf.metric_name?.trim()) && leaf.current_value != null;
}

function whyItMattersNarrative(data: SignalDetailV1): string | null {
  return (
    cleanCardSummary(data.rule_summary) ||
    cleanCardSummary(data.explanation) ||
    cleanCardSummary(data.description)
  );
}

function SignalFormulaBlock({ data }: { data: SignalDetailV1 }) {
  const formula = data.rule_formula?.trim() || data.rule_text?.trim() || null;
  const trigger = data.trigger_metric;
  const observed =
    trigger?.current_value != null
      ? `${trigger.metric_code} = ${formatMetricValue(trigger.current_value, trigger.unit)}`
      : null;

  if (!formula && !observed) return null;

  return (
    <div className="mt-3 rounded-xl border border-line/50 bg-surface-2/30 px-4 py-3">
      <div className="text-[11px] uppercase tracking-wider text-ink-soft mb-1">Formula</div>
      {formula && (
        <p className="text-sm font-medium text-ink">
          {data.rule_formula?.trim() || data.rule_text}
        </p>
      )}
      {observed && (
        <p className={clsx("text-xs font-mono text-ink-mute", formula && "mt-1")}>{observed}</p>
      )}
    </div>
  );
}

export function SignalDetailPage() {
  const { signalId } = useParams<{ signalId: string }>();
  const navigate = useNavigate();

  const { data, isLoading } = useQuery({
    queryKey: ["signal", signalId],
    queryFn: () => api<SignalDetailV1>(`/v1/signals/${signalId}`),
    enabled: !!signalId,
  });

  const sourceRefs = useMemo(
    () =>
      data
        ? uniqueSourceRefs(
            data.evidence,
            data.document_id
              ? { documentId: data.document_id, label: data.document?.document_title ?? null }
              : null,
          )
        : [],
    [data],
  );

  if (isLoading) return <PageLoader />;
  if (!data) return <div className="text-ink-mute">Signal not found.</div>;

  if (!data.company) return <div className="text-ink-mute">Signal not found.</div>;

  const symbol = companySymbol(data.company);
  const title = data.headline?.trim() || data.signal_name;
  const narrative = whyItMattersNarrative(data);
  const ruleCodes = data.rule_metric_codes ?? [];
  const ruleLeaves = data.rule_leaves ?? [];
  const renderableLeaves = ruleLeaves.filter(isRenderableRuleLeaf);
  const triggerCode = data.trigger_metric?.metric_code ?? data.primary_metric?.metric_code;
  const showWhyFired = Boolean(
    data.rule_summary ||
      data.rule_text ||
      renderableLeaves.length > 0 ||
      data.trigger_metric,
  );
  const suggestedActions = CATEGORY_ACTIONS[data.signal_category] ?? ["review_metric_comparisons"];

  return (
    <div className="w-full min-w-0 space-y-5">
      <BackButton fallback="/signals" />

      {/* Verdict strip */}
      <section className="card p-5 md:p-6">
        <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="text-[11px] uppercase tracking-wider text-ink-soft">
              {data.signal_category.replace(/_/g, " ")} · {data.signal_code.replace(/_/g, " ")}
            </div>
            <h1 className="text-xl md:text-2xl font-semibold tracking-tight mt-1 leading-snug">
              {title}
            </h1>

            <SignalMetaLinks
              company={data.company}
              period={data.period ?? null}
              event={data.event}
              symbol={symbol}
            />
          </div>

          <div className="flex flex-wrap gap-2 w-full lg:w-auto shrink-0">
            <SignalBadge direction={data.direction} size="md" />
            <SeverityBadge level={data.severity} size="md" />
          </div>
        </div>
      </section>

      {narrative && (
        <section className="card p-5 md:p-6">
          <h2 className="text-xs uppercase tracking-wider text-ink-soft mb-2">Why it matters</h2>
          <p className="text-[15px] leading-relaxed text-ink">{narrative}</p>
          <SignalFormulaBlock data={data} />
          {sourceRefs.length > 0 && <SourceDocumentLinks refs={sourceRefs} className="mt-3" />}
        </section>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
        <div className="xl:col-span-2 space-y-5 min-w-0">
          {showWhyFired && (
            <section className="card p-5 md:p-6">
              <h2 className="text-base font-semibold mb-3">Why this fired</h2>
              {data.rule_summary && (
                <p className="text-sm text-ink-mute leading-relaxed">{data.rule_summary}</p>
              )}
              {!data.rule_summary && data.rule_text && (
                <p className="text-sm text-ink-mute leading-relaxed">{data.rule_text}</p>
              )}

              {renderableLeaves.length > 0 ? (
                <div
                  className={clsx(
                    "grid grid-cols-1 sm:grid-cols-2 gap-2",
                    (data.rule_summary || data.rule_text) && "mt-4",
                  )}
                >
                  {renderableLeaves.map((leaf) => (
                    <RuleLeafRow key={leaf.metric_code} leaf={leaf} evidence={data.evidence} />
                  ))}
                </div>
              ) : (
                data.trigger_metric && (
                  <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-2">
                    <div className="card-2 p-3 col-span-2 sm:col-span-1">
                      <div className="text-[11px] text-ink-soft mb-0.5">Trigger metric</div>
                      <div className="text-xs text-ink-mute">{data.trigger_metric.metric_name}</div>
                    </div>
                    <div className="card-2 p-3">
                      <div className="text-[11px] text-ink-soft mb-0.5">Current</div>
                      <div className="text-base font-semibold num">
                        {formatMetricValue(
                          data.trigger_metric.current_value,
                          data.trigger_metric.unit,
                        )}
                        <EvidenceInlineLinks
                          items={evidenceMatchingLabel(
                            data.evidence,
                            data.trigger_metric.metric_code,
                            data.trigger_metric.metric_name,
                          )}
                        />
                      </div>
                    </div>
                    <div className="card-2 p-3">
                      <div className="text-[11px] text-ink-soft mb-0.5">Prior</div>
                      <div className="text-base font-semibold num text-ink-soft">
                        {formatMetricValue(
                          data.trigger_metric.previous_value,
                          data.trigger_metric.unit,
                        )}
                      </div>
                    </div>
                    <div className="card-2 p-3">
                      <div className="text-[11px] text-ink-soft mb-0.5">Change</div>
                      <div
                        className={clsx(
                          "text-base font-semibold num",
                          deltaTone(formatMetricChange(data.trigger_metric)),
                        )}
                      >
                        {formatMetricChange(data.trigger_metric) ?? "—"}
                      </div>
                    </div>
                  </div>
                )
              )}
            </section>
          )}

          {data.metric_comparisons.length > 0 && (
            <section className="card overflow-hidden">
              <div className="px-5 py-4 border-b border-line/60">
                <h2 className="text-base font-semibold">Financial context</h2>
                <p className="text-xs text-ink-soft mt-0.5">
                  {data.period
                    ? `${data.period.display_label} vs same quarter prior year`
                    : "Latest quarter vs same quarter prior year"}
                  {ruleCodes.length > 0 && " · rule metrics highlighted"}
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
                      const highlight = isRuleMetric(row.metric_code, ruleCodes, triggerCode);
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
                                rule
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

          {data.event && (
            <section className="card p-5 md:p-6">
              <div className="flex items-baseline justify-between gap-3">
                <h2 className="text-base font-semibold">Related event</h2>
                {symbol && (
                  <button
                    type="button"
                    onClick={() => navigate(`/company/${symbol}/event/${data.event!.event_id}`)}
                    className="text-xs text-ink-soft hover:text-ink"
                  >
                    Open event
                    <ChevronRight size={14} className="inline" />
                  </button>
                )}
              </div>
              <p className="text-sm text-ink-mute mt-0.5">
                {data.event.event_title} · {formatDate(data.event.event_date)}
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                {data.event.overall_signal && <SignalBadge direction={data.event.overall_signal} />}
                {data.event.overall_severity && (
                  <SeverityBadge level={data.event.overall_severity} />
                )}
              </div>
              {data.event.summary_text && (
                <p className="text-sm leading-relaxed text-ink mt-3 line-clamp-3">
                  {data.event.summary_text}
                </p>
              )}
              {(data.event.main_issue || data.event.watch_next) && (
                <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3">
                  {data.event.main_issue && (
                    <div className="rounded-xl bg-surface-2 border border-line/60 p-3">
                      <div className="text-[11px] uppercase tracking-wider text-ink-soft">
                        {mainIssueLabel(data.event.overall_signal)}
                      </div>
                      <p className="text-sm mt-1">{data.event.main_issue}</p>
                    </div>
                  )}
                  {data.event.watch_next && (
                    <div className="rounded-xl bg-neutral-bg border border-neutral/30 p-3">
                      <div className="text-[11px] uppercase tracking-wider text-neutral">
                        Watch next
                      </div>
                      <p className="text-sm mt-1">{data.event.watch_next}</p>
                    </div>
                  )}
                </div>
              )}
            </section>
          )}
        </div>

        <div className="space-y-5 min-w-0">
          {suggestedActions.length > 0 && (
            <section className="card p-5">
              <h2 className="text-base font-semibold mb-3">Suggested actions</h2>
              <div className="flex flex-wrap gap-1.5">
                {suggestedActions.map((action) => (
                  <span key={action} className="chip-neutral text-[11px]">
                    <ArrowUpRight size={11} />
                    {ACTION_LABELS[action] ?? action.replace(/_/g, " ")}
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

          {data.related_signals.length > 0 && (
            <section className="card p-5">
              <h2 className="text-base font-semibold mb-3">
                Other signals
                {data.company?.short_name && (
                  <span className="text-ink-mute font-normal"> · {data.company.short_name}</span>
                )}
              </h2>
              <div className="divide-y divide-line/50">
                {data.related_signals.map((s) => (
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
        </div>
      </div>
    </div>
  );
}
