import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, FileText, Layers3 } from "lucide-react";
import { api } from "@/api/client";
import type {
  EventDetail as EventDetailT,
  ExtractedValue,
  MetricValue,
  QuarterDocumentSection,
} from "@/api/types";
import { EventSignalList } from "@/components/signals/EventSignalList";
import { PageLoader } from "@/components/common/Spinner";
import { Empty } from "@/components/common/Empty";
import { BackButton } from "@/components/common/BackButton";
import {
  basisLabel,
  eventTypeLabel,
  formatDate,
  formatMetricValue,
  formatPeriodLabel,
  inputScopeLabel,
  resolveEventDisplayTitle,
} from "@/lib/format";
import { FactSourceLink } from "@/components/common/FactSourceLink";
import { MetricFormulaInfo } from "@/components/metrics/MetricFormulaInfo";

const METRIC_GROUP_ORDER = [
  "growth",
  "margin",
  "profit_quality",
  "earnings_quality",
  "cash_flow",
  "cash_quality",
  "working_capital",
  "debt",
  "leverage",
  "liquidity",
  "returns",
  "efficiency",
  "orders",
  "operating_kpi",
  "segment",
  "guidance",
  "other",
];

const FACT_GROUP_ORDER = [
  "financial_highlight",
  "profit_and_loss",
  "balance_sheet",
  "cash_flow",
  "equity",
  "segment_performance",
  "segment",
  "business_kpi",
  "order_book_pipeline",
  "guidance_outlook",
  "capex_capacity",
  "commentary_risk_outlook",
  "strategic_initiative",
  "auditor_review",
  "accounting_disclosure",
  "other",
];

const DIMENSION_LABELS: Record<string, string> = {
  segment: "Segment",
  geography: "Geography",
  product: "Product",
  channel: "Channel",
  project: "Project",
  customer_type: "Customer",
  metric_context: "Context",
};

function categoryGroupLabel(value: string | null | undefined): string {
  if (!value) return "Other";
  return value.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function groupMetricsByCategory(metrics: MetricValue[]) {
  const byGroup = new Map<string, { key: string; label: string; items: MetricValue[] }>();

  for (const metric of metrics) {
    const key = metric.category || "other";
    const group = byGroup.get(key) ?? { key, label: categoryGroupLabel(key), items: [] };
    group.items.push(metric);
    byGroup.set(key, group);
  }

  return [...byGroup.values()].sort((a, b) => {
    const aRank = METRIC_GROUP_ORDER.indexOf(a.key);
    const bRank = METRIC_GROUP_ORDER.indexOf(b.key);
    const safeARank = aRank === -1 ? METRIC_GROUP_ORDER.length : aRank;
    const safeBRank = bRank === -1 ? METRIC_GROUP_ORDER.length : bRank;
    return safeARank - safeBRank || a.label.localeCompare(b.label);
  });
}

function factGroupKey(fact: ExtractedValue): string {
  return fact.category || fact.statement?.toLowerCase() || "other";
}

function factGroupLabel(fact: ExtractedValue): string {
  return fact.group || categoryGroupLabel(fact.category || fact.statement);
}

function groupFactsByStatement(facts: ExtractedValue[]) {
  const byGroup = new Map<string, { key: string; label: string; items: ExtractedValue[] }>();

  for (const fact of facts) {
    const key = factGroupKey(fact);
    const group = byGroup.get(key) ?? { key, label: factGroupLabel(fact), items: [] };
    group.items.push(fact);
    byGroup.set(key, group);
  }

  return [...byGroup.values()].sort((a, b) => {
    const aRank = FACT_GROUP_ORDER.indexOf(a.key);
    const bRank = FACT_GROUP_ORDER.indexOf(b.key);
    const safeARank = aRank === -1 ? FACT_GROUP_ORDER.length : aRank;
    const safeBRank = bRank === -1 ? FACT_GROUP_ORDER.length : bRank;
    return safeARank - safeBRank || a.label.localeCompare(b.label);
  });
}

function displayToken(value: string | null | undefined): string {
  if (!value) return "";
  return value.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function factDimensionEntries(fact: ExtractedValue) {
  const entries: { key: string; label: string; value: string }[] = [];
  const scopeLevel = fact.scope_level;
  const scopeName = fact.scope_name;

  if (scopeLevel && scopeLevel !== "company" && scopeLevel !== "unknown") {
    entries.push({
      key: "scope",
      label: displayToken(scopeLevel),
      value: displayToken(scopeName || fact[scopeLevel as keyof ExtractedValue]?.toString()),
    });
  } else if (scopeLevel === "company") {
    entries.push({ key: "scope", label: "Scope", value: "Company" });
  }

  for (const key of [
    "segment",
    "geography",
    "product",
    "channel",
    "project",
    "customer_type",
    "metric_context",
  ] as const) {
    const raw = fact[key];
    if (!raw) continue;
    if (entries.some((entry) => entry.value.toLowerCase() === displayToken(raw).toLowerCase())) {
      continue;
    }
    entries.push({
      key,
      label: DIMENSION_LABELS[key],
      value: displayToken(raw),
    });
  }

  return entries;
}

function factValueDisplay(fact: ExtractedValue): string {
  if (
    fact.value_lower != null &&
    fact.value_upper != null &&
    fact.value_lower !== fact.value_upper
  ) {
    return `${formatMetricValue(fact.value_lower, fact.unit)} - ${formatMetricValue(
      fact.value_upper,
      fact.unit,
    )}`;
  }
  if (fact.value_numeric != null) return formatMetricValue(fact.value_numeric, fact.unit);
  if (fact.value_text) return fact.value_text;
  return "—";
}

function isLongTextFact(fact: ExtractedValue): boolean {
  return fact.value_numeric == null && Boolean(fact.value_text);
}

function sentimentClass(sentiment: string | null | undefined): string {
  const key = sentiment?.toLowerCase();
  if (key === "positive") return "chip-positive";
  if (key === "negative") return "chip-negative";
  if (key === "mixed") return "chip-mixed";
  return "chip-neutral";
}

function FactLineItem({ fact }: { fact: ExtractedValue }) {
  const dimensions = factDimensionEntries(fact);

  return (
    <div className="min-w-0">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-ink-mute">{fact.value_name}</span>
        {fact.fact_type && (
          <span className="chip-neutral text-[10px]">{displayToken(fact.fact_type)}</span>
        )}
        {fact.sentiment && (
          <span className={`${sentimentClass(fact.sentiment)} text-[10px]`}>
            {displayToken(fact.sentiment)}
          </span>
        )}
      </div>
      {dimensions.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {dimensions.map((entry) => (
            <span key={`${entry.key}:${entry.value}`} className="chip-neutral text-[10px]">
              {entry.label}: {entry.value}
            </span>
          ))}
          {fact.is_explicit_guidance ? (
            <span className="chip-neutral text-[10px]">Explicit guidance</span>
          ) : null}
        </div>
      )}
    </div>
  );
}

function PresentationSummaryPanel({ section }: { section: QuarterDocumentSection }) {
  const summary = section.presentation_summary;
  if (!summary) return null;

  const segmentCount = summary.segments.length;
  const scopeEntries = Object.entries(summary.scope_counts ?? {}).sort((a, b) => b[1] - a[1]);
  const factTypeEntries = Object.entries(summary.fact_type_counts ?? {}).sort((a, b) => b[1] - a[1]);
  const confidencePct =
    summary.average_confidence == null ? null : Math.round(summary.average_confidence * 100);

  return (
    <section className="card overflow-hidden">
      <div className="px-5 py-4 border-b border-line/60">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2">
            <Layers3 size={16} className="text-ink-soft shrink-0" />
            <div>
              <h3 className="text-base font-semibold">Presentation structure</h3>
              <p className="text-xs text-ink-soft mt-0.5">
                Business-context facts with company, segment, and guidance scope preserved.
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="chip-neutral">{segmentCount} segments</span>
            <span className="chip-neutral">{summary.guidance_count} guidance facts</span>
            {confidencePct != null && <span className="chip-neutral">{confidencePct}% avg confidence</span>}
          </div>
        </div>
      </div>
      <div className="grid gap-0 md:grid-cols-3 md:divide-x md:divide-line/50">
        <div className="px-5 py-4">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-ink-soft">
            Detected segments
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {summary.segments.length > 0 ? (
              summary.segments.slice(0, 12).map((segment) => (
                <span key={segment.slug ?? segment.name} className="chip-neutral">
                  {segment.name}
                </span>
              ))
            ) : (
              <span className="text-sm text-ink-soft">None detected</span>
            )}
          </div>
        </div>
        <div className="border-t border-line/50 px-5 py-4 md:border-t-0">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-ink-soft">
            Scope mix
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {scopeEntries.length > 0 ? (
              scopeEntries.map(([key, count]) => (
                <span key={key} className="chip-neutral">
                  {displayToken(key)}: {count}
                </span>
              ))
            ) : (
              <span className="text-sm text-ink-soft">No scoped facts</span>
            )}
          </div>
        </div>
        <div className="border-t border-line/50 px-5 py-4 md:border-t-0">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-ink-soft">
            Fact types
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {factTypeEntries.length > 0 ? (
              factTypeEntries.map(([key, count]) => (
                <span key={key} className="chip-neutral">
                  {displayToken(key)}: {count}
                </span>
              ))
            ) : (
              <span className="text-sm text-ink-soft">No type labels</span>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

function EmptySectionBlock({ title, description }: { title: string; description: string }) {
  return (
    <section className="card p-5">
      <h3 className="text-base font-semibold">{title}</h3>
      <p className="text-sm text-ink-mute mt-1">{description}</p>
    </section>
  );
}

function MetricsPanel({ metrics }: { metrics: MetricValue[] }) {
  const metricGroups = useMemo(() => groupMetricsByCategory(metrics), [metrics]);
  const [collapsedMetricGroups, setCollapsedMetricGroups] = useState<Set<string>>(() => new Set());

  const toggleMetricGroup = (groupKey: string) => {
    setCollapsedMetricGroups((current) => {
      const next = new Set(current);
      if (next.has(groupKey)) next.delete(groupKey);
      else next.add(groupKey);
      return next;
    });
  };

  if (metrics.length === 0) {
    return (
      <EmptySectionBlock
        title="Computed metrics"
        description="No metrics were computed for this document category."
      />
    );
  }

  return (
    <section className="card overflow-hidden">
      <div className="px-5 py-4 border-b border-line/60">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-base font-semibold">Computed metrics</h3>
          {metricGroups.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              {metricGroups.map((group) => (
                <span key={group.key} className="chip-neutral text-[10px]">
                  {group.label}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
      <div className="md:hidden">
        {metricGroups.map((group) => {
          const expanded = !collapsedMetricGroups.has(group.key);

          return (
            <section key={group.key} className="border-t border-line/40 first:border-t-0">
              <button
                type="button"
                className="flex w-full items-center justify-between gap-3 bg-surface-2/40 px-5 py-2 text-left hover:bg-surface-2/70 transition-colors"
                onClick={() => toggleMetricGroup(group.key)}
                aria-expanded={expanded}
              >
                <span className="flex min-w-0 items-center gap-2">
                  <ChevronDown
                    size={14}
                    className={`shrink-0 text-ink-soft transition-transform ${expanded ? "" : "-rotate-90"}`}
                  />
                  <span className="truncate text-[11px] font-semibold uppercase tracking-wider text-ink-soft">
                    {group.label}
                  </span>
                </span>
                <span className="text-[11px] text-ink-soft num">{group.items.length}</span>
              </button>
              {expanded && (
                <div className="divide-y divide-line/40">
                  {group.items.map((m) => (
                    <div
                      key={m.metric_code}
                      className="px-5 py-3 flex items-center justify-between gap-4"
                    >
                      <span className="flex min-w-0 items-center gap-2">
                        <span className="text-ink-mute min-w-0">{m.metric_name}</span>
                        <MetricFormulaInfo
                          calculationData={m.calculation_data}
                          metricName={m.metric_name}
                        />
                      </span>
                      <span className="num text-ink font-medium whitespace-nowrap shrink-0">
                        {formatMetricValue(m.metric_value, m.unit)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </section>
          );
        })}
      </div>
      <table className="hidden md:table w-full text-sm">
        {metricGroups.map((group) => {
          const expanded = !collapsedMetricGroups.has(group.key);

          return (
            <tbody key={group.key}>
              <tr className="border-t border-line/60 first:border-t-0 bg-surface-2/40">
                <td colSpan={2} className="p-0">
                  <button
                    type="button"
                    className="flex w-full items-center justify-between gap-3 px-5 py-2 text-left hover:bg-surface-2/70 transition-colors"
                    onClick={() => toggleMetricGroup(group.key)}
                    aria-expanded={expanded}
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      <ChevronDown
                        size={14}
                        className={`shrink-0 text-ink-soft transition-transform ${expanded ? "" : "-rotate-90"}`}
                      />
                      <span className="truncate text-[11px] font-semibold uppercase tracking-wider text-ink-soft">
                        {group.label}
                      </span>
                    </span>
                    <span className="text-[11px] text-ink-soft num">
                      {group.items.length} {group.items.length === 1 ? "item" : "items"}
                    </span>
                  </button>
                </td>
              </tr>
              {expanded &&
                group.items.map((m) => (
                  <tr key={m.metric_code} className="border-t border-line/40">
                    <td className="px-5 py-2.5 text-ink-mute">
                      <span className="flex items-center gap-2">
                        <span>{m.metric_name}</span>
                        <MetricFormulaInfo
                          calculationData={m.calculation_data}
                          metricName={m.metric_name}
                        />
                      </span>
                    </td>
                    <td className="px-5 py-2.5 text-right num text-ink font-medium">
                      {formatMetricValue(m.metric_value, m.unit)}
                    </td>
                  </tr>
                ))}
            </tbody>
          );
        })}
      </table>
    </section>
  );
}

function FactsPanel({
  facts,
  factPeriods,
  activeFactPeriodEnd,
  fallbackDocumentId,
}: {
  facts: ExtractedValue[];
  factPeriods: { period_end: string; period_label: string | null; scope: string; facts_count: number }[];
  activeFactPeriodEnd: string | null;
  fallbackDocumentId: string | null;
}) {
  const factGroups = useMemo(() => groupFactsByStatement(facts), [facts]);
  const [collapsedFactGroups, setCollapsedFactGroups] = useState<Set<string>>(() => new Set());
  const activeFactPeriod = factPeriods.find((period) => period.period_end === activeFactPeriodEnd);

  const toggleFactGroup = (groupKey: string) => {
    setCollapsedFactGroups((current) => {
      const next = new Set(current);
      if (next.has(groupKey)) next.delete(groupKey);
      else next.add(groupKey);
      return next;
    });
  };

  if (facts.length === 0) {
    return (
      <EmptySectionBlock
        title="Extracted facts"
        description="No facts were extracted for this document category."
      />
    );
  }

  return (
    <section className="card overflow-hidden">
      <div className="px-5 py-4 border-b border-line/60">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="text-base font-semibold">Extracted facts</h3>
            <p className="text-xs text-ink-soft mt-0.5">
              {activeFactPeriod
                ? `${inputScopeLabel(activeFactPeriod.scope)} · ${
                    activeFactPeriod.period_label ?? formatPeriodLabel(activeFactPeriod.period_end)
                  }`
                : "Values pulled from the document."}
            </p>
          </div>
          {factGroups.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              {factGroups.map((group) => (
                <span key={group.key} className="chip-neutral text-[10px]">
                  {group.label}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
      <div className="md:hidden">
        {factGroups.map((group) => {
          const expanded = !collapsedFactGroups.has(group.key);

          return (
            <section key={group.key} className="border-t border-line/40 first:border-t-0">
              <button
                type="button"
                className="flex w-full items-center justify-between gap-3 bg-surface-2/40 px-5 py-2 text-left hover:bg-surface-2/70 transition-colors"
                onClick={() => toggleFactGroup(group.key)}
                aria-expanded={expanded}
              >
                <span className="flex min-w-0 items-center gap-2">
                  <ChevronDown
                    size={14}
                    className={`shrink-0 text-ink-soft transition-transform ${expanded ? "" : "-rotate-90"}`}
                  />
                  <span className="truncate text-[11px] font-semibold uppercase tracking-wider text-ink-soft">
                    {group.label}
                  </span>
                </span>
                <span className="text-[11px] text-ink-soft num">{group.items.length}</span>
              </button>
              {expanded && (
                <div className="divide-y divide-line/40">
                  {group.items.map((f) => (
                    <div
                      key={`${f.observation_id ?? f.value_code}-${f.basis ?? ""}-${f.period_end ?? ""}-${f.source_page ?? ""}`}
                      className="px-5 py-3.5"
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div className="min-w-0">
                          <FactLineItem fact={f} />
                          {f.basis && (
                            <span className="mt-1 inline-flex text-[11px] text-ink-soft">
                              {basisLabel(f.basis)}
                            </span>
                          )}
                        </div>
                        <div
                          className={`text-right text-ink font-medium shrink-0 ${
                            isLongTextFact(f)
                              ? "max-w-[52%] whitespace-normal text-sm leading-snug"
                              : "num whitespace-nowrap"
                          }`}
                        >
                          {factValueDisplay(f)}
                        </div>
                      </div>
                      <div className="mt-2">
                        <FactSourceLink documentId={f.document_id ?? fallbackDocumentId} fact={f} />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>
          );
        })}
      </div>
      <div className="hidden md:block overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-[11px] uppercase tracking-wider text-ink-soft">
            <tr>
              <th className="px-5 py-2 text-left font-medium">Line item</th>
              <th className="px-5 py-2 text-right font-medium">Value</th>
              <th className="px-5 py-2 text-center font-medium w-20">Source</th>
            </tr>
          </thead>
          {factGroups.map((group) => {
            const expanded = !collapsedFactGroups.has(group.key);

            return (
              <tbody key={group.key}>
                <tr className="border-t border-line/60 bg-surface-2/40">
                  <td colSpan={3} className="p-0">
                    <button
                      type="button"
                      className="flex w-full items-center justify-between gap-3 px-5 py-2 text-left hover:bg-surface-2/70 transition-colors"
                      onClick={() => toggleFactGroup(group.key)}
                      aria-expanded={expanded}
                    >
                      <span className="flex min-w-0 items-center gap-2">
                        <ChevronDown
                          size={14}
                          className={`shrink-0 text-ink-soft transition-transform ${expanded ? "" : "-rotate-90"}`}
                        />
                        <span className="truncate text-[11px] font-semibold uppercase tracking-wider text-ink-soft">
                          {group.label}
                        </span>
                      </span>
                      <span className="text-[11px] text-ink-soft num">
                        {group.items.length} {group.items.length === 1 ? "item" : "items"}
                      </span>
                    </button>
                  </td>
                </tr>
                {expanded &&
                  group.items.map((f) => (
                    <tr
                      key={`${f.observation_id ?? f.value_code}-${f.basis ?? ""}-${f.period_end ?? ""}-${f.source_page ?? ""}`}
                      className="border-t border-line/40 align-top"
                    >
                      <td className="px-5 py-2.5">
                        <FactLineItem fact={f} />
                        {f.basis && (
                          <span className="mt-1 inline-flex text-[11px] text-ink-soft">
                            {basisLabel(f.basis)}
                          </span>
                        )}
                      </td>
                      <td
                        className={`px-5 py-2.5 text-right text-ink font-medium ${
                          isLongTextFact(f)
                            ? "max-w-[360px] whitespace-normal text-sm leading-snug"
                            : "num whitespace-nowrap"
                        }`}
                      >
                        {factValueDisplay(f)}
                      </td>
                      <td className="px-5 py-2.5 w-20 text-center">
                        <FactSourceLink documentId={f.document_id ?? fallbackDocumentId} fact={f} />
                      </td>
                    </tr>
                  ))}
              </tbody>
            );
          })}
        </table>
      </div>
    </section>
  );
}

function QuarterDocumentSectionPanel({ section }: { section: QuarterDocumentSection }) {
  const documentId = section.document?.id ?? section.event?.document_id ?? null;
  const sourceHref = documentId ? `/documents/${documentId}` : null;
  const eventDate = section.event?.event_date ?? section.document?.ingested_at ?? null;

  return (
    <section className="space-y-3">
      <header className="card p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-[11px] font-semibold uppercase tracking-wider text-ink-soft">
              {section.label}
            </div>
            <h2 className="mt-1 text-lg font-semibold text-ink leading-snug">
              {section.document?.title || section.event?.title || section.label}
            </h2>
            <div className="mt-1 text-sm text-ink-soft">{formatDate(eventDate)}</div>
          </div>
          <div className="flex flex-wrap items-center gap-2 shrink-0">
            <span className="chip-neutral">{section.counts.facts} facts</span>
            <span className="chip-neutral">{section.counts.metrics} metrics</span>
            <span className="chip-neutral">{section.counts.signals} signals</span>
            {sourceHref && (
              <Link
                to={sourceHref}
                className="inline-flex items-center gap-1.5 text-sm text-ink-mute hover:text-ink"
              >
                <FileText size={14} /> Source
              </Link>
            )}
          </div>
        </div>
      </header>

      {section.document_type === "INVESTOR_PRESENTATION" && (
        <PresentationSummaryPanel section={section} />
      )}

      {section.signals.length > 0 ? (
        <EventSignalList signals={section.signals} title="Signals fired" />
      ) : (
        <EmptySectionBlock
          title="Signals fired"
          description="No signals fired for this document category."
        />
      )}
      <MetricsPanel metrics={section.metrics} />
      <FactsPanel
        facts={section.facts}
        factPeriods={section.fact_periods}
        activeFactPeriodEnd={section.selected_fact_period_end}
        fallbackDocumentId={documentId}
      />
    </section>
  );
}

export function EventDetail() {
  const { ticker, eventId } = useParams<{ ticker: string; eventId: string }>();

  const { data, isLoading } = useQuery({
    queryKey: ["event", eventId],
    queryFn: () => api<EventDetailT>(`/events/${eventId}`),
    enabled: !!eventId,
  });

  if (isLoading) return <PageLoader />;
  if (!data) return <div className="text-ink-mute">Event not found.</div>;

  const { event, company, facts, metrics, signals } = data;
  const companyEventTicker = ticker ?? company?.ticker ?? "";
  const relatedDocumentEvents = (data.related_events ?? []).filter((item) => item.document_id);
  const factPeriods = data.fact_periods ?? [];
  const allDocumentSections =
    data.document_sections && data.document_sections.length > 0
      ? data.document_sections
      : [
          {
            key: event.id,
            document_type: event.event_type,
            label: resolveEventDisplayTitle(event.event_type, event.title),
            event,
            document: null,
            facts,
            fact_periods: factPeriods,
            selected_fact_period_end: data.selected_fact_period_end,
            metrics,
            signals,
            counts: {
              facts: facts.length,
              metrics: metrics.length,
              signals: signals.length,
            },
          },
        ];
  const documentSections = event.document_id
    ? allDocumentSections.filter(
        (section) =>
          section.event?.id === event.id || section.document?.id === event.document_id,
      )
    : allDocumentSections;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <BackButton fallback={ticker ? `/company/${ticker}` : "/companies"} />

      <header className="card p-5 space-y-2">
        <div className="flex items-center justify-between gap-3">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-soft">
            {eventTypeLabel(event.event_type)}
          </span>
          {event.period_label && <span className="chip-neutral">{event.period_label}</span>}
        </div>
        <h1 className="text-xl font-semibold text-ink leading-snug">
          {company?.name}
          {event.period_label && (
            <span className="text-ink-mute font-normal"> · {event.period_label}</span>
          )}
        </h1>
        <div className="text-sm text-ink-soft">{formatDate(event.event_date)}</div>
        {relatedDocumentEvents.length > 1 ? (
          <div className="flex flex-wrap items-center gap-3">
            {relatedDocumentEvents.map((item) => (
              <Link
                key={item.id}
                to={`/company/${companyEventTicker}/event/${item.id}`}
                className="inline-flex items-center gap-1.5 text-sm text-ink-mute hover:text-ink"
              >
                <FileText size={14} />
                {resolveEventDisplayTitle(item.event_type, item.title)}
              </Link>
            ))}
          </div>
        ) : event.document_id ? (
          <Link
            to={`/documents/${event.document_id}`}
            className="inline-flex items-center gap-1.5 text-sm text-ink-mute hover:text-ink"
          >
            <FileText size={14} /> View source document
          </Link>
        ) : null}
      </header>

      {documentSections.length > 0 ? (
        <div className="space-y-8">
          {documentSections.map((section) => (
            <QuarterDocumentSectionPanel key={section.key} section={section} />
          ))}
        </div>
      ) : (
        <Empty title="No document categories" description="No processed documents were found for this quarter." />
      )}
    </div>
  );
}
