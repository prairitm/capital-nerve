import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { api } from "@/api/client";
import type { SignalDetail as SignalDetailT } from "@/api/types";
import { PageLoader } from "@/components/common/Spinner";
import { BackButton } from "@/components/common/BackButton";
import { FactSourceLink } from "@/components/common/FactSourceLink";
import { Pagination, usePagination } from "@/components/common/Pagination";
import { SignalBadge } from "@/components/common/SignalBadge";
import { SeverityBadge } from "@/components/common/SeverityBadge";
import {
  buildTriggerMetricRows,
  buildTriggerNarrative,
  humanizeRuleText,
  signalCategoryLabel,
} from "@/lib/signals";
import { basisLabel, formatDate, formatMetricValue, inputScopeLabel } from "@/lib/format";

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
  const triggerNarrative = buildTriggerNarrative(
    data.rule_text,
    data.trigger_values,
    data.referenced_metrics,
  );
  const showWhyFired = Boolean(data.rule_text || metricRows.length > 0);
  const inputFacts = data.input_facts ?? [];

  return (
    <div className="max-w-3xl mx-auto space-y-5">
      <BackButton fallback="/signals" />

      <header className="card p-5 space-y-3">
        <div className="flex items-center justify-between gap-3">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-soft">
            {signalCategoryLabel(data.category)}
          </span>
          <div className="flex items-center gap-2">
            <SignalBadge direction={data.direction} />
            <SeverityBadge level={data.severity} />
          </div>
        </div>
        <h1 className="text-2xl font-semibold text-ink leading-tight">{data.signal_name}</h1>
        {(data.company || data.event) && (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
            {data.company && (
              <Link
                to={ticker ? `/company/${ticker}` : "#"}
                className="inline-flex items-center gap-1 text-ink-mute hover:text-ink"
              >
                {data.company.name}
                {ticker && <span className="text-ink-soft">· {ticker}</span>}
                <ChevronRight size={14} />
              </Link>
            )}
            {data.event && ticker && (
              <Link
                to={`/company/${ticker}/event/${data.event.id}`}
                className="inline-flex items-center gap-1 text-ink-mute hover:text-ink"
              >
                <span className="font-medium text-ink">
                  {data.event.period_label || data.event.title || data.event.event_type}
                </span>
                {data.event.event_date && (
                  <span className="text-ink-soft">· {formatDate(data.event.event_date)}</span>
                )}
                <ChevronRight size={14} />
              </Link>
            )}
          </div>
        )}
        {data.description && (
          <p className="text-sm text-ink-mute leading-relaxed">{data.description}</p>
        )}
      </header>

      {showWhyFired && (
        <section className="card overflow-hidden">
          <div className="px-5 py-4 border-b border-line/60">
            <h2 className="text-base font-semibold">Why this fired</h2>
          </div>
          <div className="px-5 py-4 space-y-4">
            {triggerNarrative ? (
              <p className="text-sm text-ink leading-relaxed">{triggerNarrative}</p>
            ) : data.rule_text ? (
              <p className="text-sm text-ink leading-relaxed">
                {humanizeRuleText(data.rule_text, data.referenced_metrics)}
              </p>
            ) : null}

            {metricRows.length > 1 && (
              <>
                <div className="md:hidden divide-y divide-line/40 -mx-5">
                  {visibleMetricRows.map((row) => (
                    <div
                      key={row.code}
                      className="px-5 py-2.5 flex items-center justify-between gap-4"
                    >
                      <span className="text-ink-mute min-w-0">{row.name}</span>
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
                        <td className="py-2.5 text-ink-mute">{row.name}</td>
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

            {data.rule_text && triggerNarrative && (
              <p className="text-xs text-ink-soft num">
                Rule: {humanizeRuleText(data.rule_text, data.referenced_metrics)}
              </p>
            )}

            {inputFacts.length > 0 && (
              <div className="border-t border-line/40 pt-4 space-y-3">
                <h3 className="text-[11px] font-semibold uppercase tracking-wider text-ink-soft">
                  Based on
                </h3>
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
                            {fact.basis && (
                              <span className="chip-neutral text-[10px]">
                                {basisLabel(fact.basis)}
                              </span>
                            )}
                          </div>
                        </div>
                        <span className="num text-sm text-ink font-medium whitespace-nowrap shrink-0">
                          {formatMetricValue(fact.value_numeric, fact.unit)}
                        </span>
                      </div>
                      {fact.source_text && (
                        <div className="text-xs text-ink-soft">
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
          </div>
        </section>
      )}
    </div>
  );
}
