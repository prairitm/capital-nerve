import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { BarChart3, ChevronRight, FileText, Info } from "lucide-react";
import { api } from "@/api/client";
import type { SignalDetail as SignalDetailT } from "@/api/types";
import { PageLoader } from "@/components/common/Spinner";
import { BackButton } from "@/components/common/BackButton";
import { FactSourceLink } from "@/components/common/FactSourceLink";
import { Pagination, usePagination } from "@/components/common/Pagination";
import { SignalBadge } from "@/components/common/SignalBadge";
import { SeverityBadge } from "@/components/common/SeverityBadge";
import { MetricFormulaInfo } from "@/components/metrics/MetricFormulaInfo";
import {
  buildTriggerMetricRows,
  buildTriggerNarrative,
  buildStructuredRuleText,
  buildStructuredTriggerNarrative,
  humanizeRuleText,
  signalCategoryLabel,
} from "@/lib/signals";
import {
  basisLabel,
  eventTypeLabel,
  formatDate,
  formatMetricValue,
  inputScopeLabel,
  resolvePeriodLabel,
} from "@/lib/format";

export function SignalDetail() {
  const { signalId } = useParams<{ signalId: string }>();

  const { data, isLoading } = useQuery({
    queryKey: ["signal", signalId],
    queryFn: () => api<SignalDetailT>(`/signals/${signalId}`),
    enabled: !!signalId,
  });
  const metricRows = data
    ? buildTriggerMetricRows(data.trigger_values, data.referenced_metrics)
    : [];
  const metricsPagination = usePagination(metricRows, 10, signalId);
  const visibleMetricRows = metricsPagination.pageItems;

  if (isLoading) return <PageLoader />;
  if (!data) return <div className="text-ink-mute">Signal not found.</div>;

  const ticker = data.company?.ticker;
  const signalName = data.signal_name || data.title || data.signal_type;
  const periodLabel = resolvePeriodLabel(data.event?.period_label, data.event?.title);
  const triggerNarrative =
    buildTriggerNarrative(
      data.rule_text,
      data.trigger_values,
      data.referenced_metrics,
    ) || buildStructuredTriggerNarrative(data.rule, data.referenced_metrics);
  const ruleDefinition = data.rule_text
    ? humanizeRuleText(data.rule_text, data.referenced_metrics)
    : buildStructuredRuleText(data.rule, data.referenced_metrics);
  const inputFacts = data.input_facts ?? [];
  const inputFactBases = Array.from(new Set(inputFacts.map((fact) => fact.basis).filter(Boolean)));
  const primaryMetric = metricRows[0] ?? null;
  const sourceType = data.event ? eventTypeLabel(data.event.event_type) : "Source event unavailable";

  return (
    <div className="max-w-4xl mx-auto space-y-5">
      <BackButton fallback="/signals" />

      <header className="card p-5 md:p-6 space-y-4">
        <div className="flex items-center justify-between gap-3">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-soft">
            {signalCategoryLabel(data.category)}
          </span>
          <div className="flex items-center gap-2">
            <SignalBadge direction={data.direction} />
            <SeverityBadge level={data.severity} />
          </div>
        </div>
        <h1 className="text-2xl md:text-[28px] font-semibold text-ink leading-tight">{signalName}</h1>
        {data.description && (
          <p className="max-w-2xl text-sm text-ink-mute leading-6">{data.description}</p>
        )}

        <div className="grid gap-3 border-t border-line/50 pt-4 text-sm sm:grid-cols-3">
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-soft">Company</div>
            {data.company && ticker ? (
              <Link to={`/company/${ticker}`} className="mt-1 inline-flex items-center gap-1 font-medium text-ink hover:text-brand-soft">
                {data.company.name ?? ticker}<ChevronRight size={14} />
              </Link>
            ) : (
              <div className="mt-1 font-medium text-ink">{data.company?.name ?? "Not linked"}</div>
            )}
            {ticker && <div className="mt-0.5 text-xs text-ink-soft">{ticker}</div>}
          </div>
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-soft">Source</div>
            <div className="mt-1 font-medium text-ink">{sourceType}</div>
            {periodLabel && <div className="mt-0.5 text-xs text-ink-soft">{periodLabel}</div>}
          </div>
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-soft">Reported</div>
            <div className="mt-1 font-medium text-ink">{formatDate(data.event?.event_date)}</div>
            <div className="mt-0.5 text-xs text-ink-soft">Signal evidence period</div>
          </div>
        </div>
      </header>

      <section className="grid gap-px overflow-hidden rounded-2xl border border-line bg-line sm:grid-cols-3" aria-label="Signal evidence summary">
        <div className="bg-surface p-4 md:p-5">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-soft">Observed</div>
          <div className="mt-2 text-xl font-semibold text-ink num">
            {primaryMetric ? formatMetricValue(primaryMetric.value, primaryMetric.unit) : "Not linked"}
          </div>
          <div className="mt-1 text-xs text-ink-mute">{primaryMetric?.name ?? "No observed metric attached"}</div>
        </div>
        <div className="bg-surface p-4 md:p-5">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-soft">Trigger condition</div>
          <div className="mt-2 text-sm font-semibold leading-5 text-ink num">{ruleDefinition ?? "Not available"}</div>
          <div className="mt-1 text-xs text-ink-mute">Catalog rule used for detection</div>
        </div>
        <div className="bg-surface p-4 md:p-5">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-soft">Evidence</div>
          <div className="mt-2 text-xl font-semibold text-ink num">{inputFacts.length}</div>
          <div className="mt-1 text-xs text-ink-mute">{inputFacts.length === 1 ? "Linked source fact" : "Linked source facts"}</div>
        </div>
      </section>

      <section className="card overflow-hidden">
        <div className="px-5 py-4 border-b border-line/60">
          <h2 className="text-base font-semibold">Why this signal fired</h2>
          <p className="mt-1 text-xs text-ink-mute">Observed evidence compared with the signal's catalog rule.</p>
        </div>
        <div className="px-5 py-4 space-y-4">
          {triggerNarrative ? (
            <div className="flex gap-3 rounded-xl border border-line/60 bg-surface-2/50 p-4">
              <BarChart3 size={18} className="mt-0.5 shrink-0 text-brand-soft" />
              <p className="text-sm text-ink leading-6">{triggerNarrative}</p>
            </div>
          ) : ruleDefinition ? (
            <div className="flex gap-3 rounded-xl border border-line/60 bg-surface-2/50 p-4">
              <Info size={18} className="mt-0.5 shrink-0 text-ink-soft" />
              <div>
                <p className="text-sm text-ink leading-6">This signal matched the catalog condition: <span className="font-medium num">{ruleDefinition}</span>.</p>
                {metricRows.length === 0 && (
                  <p className="mt-1 text-xs leading-5 text-ink-mute">The signal record does not include a linked observed metric for this filing.</p>
                )}
              </div>
            </div>
          ) : (
            <div className="flex gap-3 rounded-xl border border-line/60 bg-surface-2/50 p-4">
              <Info size={18} className="mt-0.5 shrink-0 text-ink-soft" />
              <p className="text-sm text-ink-mute leading-6">A machine-readable trigger definition is not attached to this signal. Use the source context below to verify the underlying disclosure.</p>
            </div>
          )}

          {metricRows.length > 0 && (
            <>
              <h3 className="text-[11px] font-semibold uppercase tracking-wider text-ink-soft">Observed metrics</h3>
              <div className="md:hidden divide-y divide-line/40 -mx-5">
                {visibleMetricRows.map((row) => (
                  <div
                    key={row.code}
                    className="px-5 py-2.5 flex items-center justify-between gap-4"
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      <span className="text-ink-mute min-w-0">{row.name}</span>
                      <MetricFormulaInfo calculationData={row.calculationData} metricName={row.name} />
                    </span>
                    <span className="num text-ink font-medium whitespace-nowrap shrink-0">
                      {formatMetricValue(row.value, row.unit)}
                    </span>
                  </div>
                ))}
              </div>
              <table className="hidden md:table w-full text-sm">
                <thead>
                  <tr className="text-left text-[11px] uppercase tracking-wider text-ink-soft">
                    <th className="pb-2 font-medium">Metric</th>
                    <th className="pb-2 text-right font-medium">Value</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleMetricRows.map((row) => (
                    <tr key={row.code} className="border-t border-line/40">
                      <td className="py-2.5 text-ink-mute">
                        <span className="flex items-center gap-2">
                          <span>{row.name}</span>
                          <MetricFormulaInfo calculationData={row.calculationData} metricName={row.name} />
                        </span>
                      </td>
                      <td className="py-2.5 text-right num text-ink font-medium">
                        {formatMetricValue(row.value, row.unit)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <Pagination
                page={metricsPagination.page}
                pageCount={metricsPagination.pageCount}
                pageStart={metricsPagination.pageStart}
                pageEnd={metricsPagination.pageEnd}
                total={metricRows.length}
                onPageChange={metricsPagination.setPage}
              />
            </>
          )}

          {ruleDefinition && triggerNarrative && (
            <p className="text-xs text-ink-soft num">
              Rule: {ruleDefinition}
            </p>
          )}

          {inputFacts.length > 0 && (
            <div className="border-t border-line/40 pt-4 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-[11px] font-semibold uppercase tracking-wider text-ink-soft">
                  Based on
                </h3>
                {inputFactBases.length > 0 && (
                  <div className="flex flex-wrap items-center gap-1.5">
                    {inputFactBases.map((basis) => (
                      <span key={basis} className="chip-neutral text-[10px]">
                        {basisLabel(basis)}
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <div className="divide-y divide-line/40 -mx-5">
                {inputFacts.map((fact) => (
                  <div
                    key={`${fact.fact_key}-${fact.scope}`}
                    className="px-5 py-3 space-y-1.5"
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="min-w-0">
                        <div className="text-sm text-ink">{fact.value_name}</div>
                        <div className="flex flex-wrap items-center gap-1.5 mt-0.5">
                          <span className="text-xs text-ink-soft">
                            {inputScopeLabel(fact.scope)}
                          </span>
                        </div>
                      </div>
                      <span className="num text-sm text-ink font-medium whitespace-nowrap shrink-0">
                        {formatMetricValue(fact.value_numeric, fact.unit)}
                      </span>
                    </div>
                    {fact.source_text && (
                      <div>
                        <FactSourceLink
                          documentId={fact.document_id ?? data.event?.document_id ?? null}
                          fact={fact}
                        />
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
          {metricRows.length === 0 && inputFacts.length === 0 && (
            <div className="border-t border-line/40 pt-4 text-xs leading-5 text-ink-mute">
              No metric values or source facts are linked to this signal record. The source event remains available for manual review.
            </div>
          )}
        </div>
      </section>

      <section className="card p-5">
        <div className="flex items-start gap-3">
          <div className="grid size-9 shrink-0 place-items-center rounded-xl bg-surface-2 text-ink-mute">
            <FileText size={17} />
          </div>
          <div className="min-w-0 flex-1">
            <h2 className="text-base font-semibold text-ink">Source context</h2>
            <p className="mt-1 text-sm leading-5 text-ink-mute">
              {data.event
                ? `${sourceType}${periodLabel ? ` · ${periodLabel}` : ""}${data.event.event_date ? ` · ${formatDate(data.event.event_date)}` : ""}`
                : "This signal is not linked to a source event."}
            </p>
            {data.event?.title && data.event.title !== periodLabel && (
              <p className="mt-2 text-xs leading-5 text-ink-soft line-clamp-2">{data.event.title}</p>
            )}
            <div className="mt-4 flex flex-wrap gap-2">
              {data.event && ticker && (
                <Link to={`/company/${ticker}/event/${data.event.id}`} className="btn-secondary">
                  Review source event<ChevronRight size={14} />
                </Link>
              )}
              {data.company && ticker && (
                <Link to={`/company/${ticker}`} className="btn-secondary">
                  Open company<ChevronRight size={14} />
                </Link>
              )}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
