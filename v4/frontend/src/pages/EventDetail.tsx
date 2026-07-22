import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, Check, ChevronDown, FileSearch, FileText, Loader2, Share2, Sparkles } from "lucide-react";
import clsx from "clsx";
import { api } from "@/api/client";
import type {
  DisplayFactGroup,
  EventDetail as EventDetailT,
  EventSummary,
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
import { MetricCard } from "@/components/common/DashboardUI";
import type { SnapshotRow } from "@/api/types";
import { rankDisplaySignals } from "@/lib/signals";

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

function filingBriefShareText(
  summary: EventSummary,
  companyName: string,
  periodLabel: string | null | undefined,
): string {
  const context = [companyName, periodLabel].filter(Boolean).join(" · ");
  return [
    context,
    summary.headline,
    summary.summary,
    "Key points",
    ...summary.key_points.map((point) => `• ${point}`),
    "Investor takeaway",
    summary.investor_takeaway,
    "AI-generated from the source filing. Review the filing before making decisions.",
  ]
    .filter(Boolean)
    .join("\n\n");
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
  if (fact.value_text) {
    return /^[A-Z][A-Z0-9_]+$/.test(fact.value_text)
      ? displayToken(fact.value_text)
      : fact.value_text;
  }
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

function presentationContext(fact: ExtractedValue): string {
  const source = `${fact.source_text ?? ""} ${fact.metric_context ?? ""}`;
  const standalone = /standalone/i.test(source) ? " · Standalone" : "";
  const quarter = source.match(/\b(Q[1-4])\s+FY\s?(\d{2,4})(?:-(\d{2}))?\b/i);
  const year = source.match(/\bFY\s?(\d{2,4})(?:-(\d{2}))?\b/i);
  const fiscalLabel = (rawYear: string, explicitEnd?: string) => {
    if (explicitEnd) return `FY${rawYear}-${explicitEnd}`;
    const endYear = Number(rawYear.length === 2 ? `20${rawYear}` : rawYear);
    return `FY${endYear - 1}-${String(endYear).slice(-2)}`;
  };
  if (quarter) return `${quarter[1].toUpperCase()} ${fiscalLabel(quarter[2], quarter[3])}${standalone}`;
  if (year) return `${fiscalLabel(year[1], year[2])}${standalone}`;
  return fact.period_end ? formatPeriodLabel(fact.period_end) : "Reported";
}

function cleanFactName(name: string): string {
  return name.replace(/^Presentation\s+/i, "").replace(/\bT D\b/g, "T&D");
}

function uniquePresentationFacts(facts: ExtractedValue[]) {
  const seen = new Set<string>();
  return facts.filter((fact) => {
    const key = [fact.value_code, fact.value_numeric, fact.value_text, fact.unit, fact.segment, presentationContext(fact)].join("|");
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function selectMetrics(
  metrics: MetricValue[],
  priority: string[] = [],
  limit = 4,
): MetricValue[] {
  const firstByCode = new Map<string, MetricValue>();
  for (const metric of metrics) {
    if (metric.metric_value == null || firstByCode.has(metric.metric_code)) continue;
    firstByCode.set(metric.metric_code, metric);
  }
  return priority
    .map((code) => firstByCode.get(code))
    .filter((metric): metric is MetricValue => Boolean(metric))
    .slice(0, limit);
}

function factPriorityScore(fact: ExtractedValue): number {
  const explicitGuidance = fact.is_explicit_guidance ? 100 : 0;
  const watchItem = fact.sentiment?.toLowerCase() === "negative" ? 40 : 0;
  const quantified = fact.value_numeric != null || /\d/.test(fact.value_text ?? "") ? 20 : 0;
  return explicitGuidance + watchItem + quantified + (fact.confidence ?? 0);
}

function selectFactsForGroup(
  facts: ExtractedValue[],
  group: DisplayFactGroup,
  dedupeCodes = false,
): ExtractedValue[] {
  const allowed = new Set(group.fact_codes);
  const ranked = uniquePresentationFacts(facts.filter((fact) => allowed.has(fact.value_code)))
    .sort((a, b) => factPriorityScore(b) - factPriorityScore(a));
  if (!dedupeCodes) return ranked.slice(0, group.max_items);
  const selected: ExtractedValue[] = [];
  const seenCodes = new Set<string>();
  for (const fact of ranked) {
    if (seenCodes.has(fact.value_code)) continue;
    seenCodes.add(fact.value_code);
    selected.push(fact);
    if (selected.length >= group.max_items) break;
  }
  return selected;
}

function DisplayMetricGrid({
  metrics,
  title = "Key indicators",
}: {
  metrics: MetricValue[];
  title?: string;
}) {
  if (metrics.length === 0) return null;
  return (
    <section className="card overflow-hidden">
      <div className="border-b border-line/60 px-5 py-4">
        <h3 className="text-base font-semibold">{title}</h3>
      </div>
      <div className="grid gap-px bg-line/60 sm:grid-cols-2 lg:grid-cols-3">
        {metrics.map((metric) => (
          <div key={metric.metric_code} className="bg-surface p-4">
            <div className="flex items-start justify-between gap-2">
              <span className="text-xs font-medium text-ink-mute">{metric.metric_name}</span>
              <MetricFormulaInfo calculationData={metric.calculation_data} metricName={metric.metric_name} />
            </div>
            <div className="mt-2 text-xl font-semibold tracking-tight text-ink num">
              {formatMetricValue(metric.metric_value, metric.unit)}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function DisplayFactGroups({
  section,
  groups,
  title,
  maxItems = 6,
  dedupeCodes = false,
}: {
  section: QuarterDocumentSection;
  groups: DisplayFactGroup[];
  title: string;
  maxItems?: number;
  dedupeCodes?: boolean;
}) {
  let remaining = maxItems;
  const populated = groups.flatMap((group) => {
    if (remaining <= 0) return [];
    const items = selectFactsForGroup(section.facts, group, dedupeCodes).slice(0, remaining);
    remaining -= items.length;
    return items.length > 0 ? [{ group, items }] : [];
  });
  if (populated.length === 0) return null;

  return (
    <section className="card overflow-hidden">
      <div className="border-b border-line/60 px-5 py-4">
        <div className="flex items-center gap-2"><Sparkles size={16} className="text-brand-soft" /><h3 className="text-base font-semibold">{title}</h3></div>
      </div>
      <div className="divide-y divide-line/50">
        {populated.map(({ group, items }) => (
          <div key={group.key} className="px-5 py-4">
            <div className="text-[11px] font-semibold uppercase tracking-wider text-brand-soft">{group.label}</div>
            {group.description && <p className="mt-1 text-xs text-ink-soft">{group.description}</p>}
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              {items.map((fact) => (
                <article key={`${group.key}-${fact.value_code}-${fact.segment ?? fact.scope_name ?? "company"}-${fact.value_text ?? fact.value_numeric}`} className="rounded-xl border border-line/70 bg-surface-2/35 p-3.5">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-xs font-medium text-ink-mute">{cleanFactName(fact.value_name)}</div>
                      <div className={clsx("mt-1 font-semibold text-ink", isLongTextFact(fact) ? "text-sm leading-6" : "text-lg num")}>{factValueDisplay(fact)}</div>
                    </div>
                    <FactSourceLink documentId={fact.document_id ?? section.document?.id ?? null} fact={fact} />
                  </div>
                  {(fact.segment || fact.scope_name || fact.sentiment) && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {(fact.segment || fact.scope_name) && <span className="chip-neutral text-[10px]">{cleanDimensionName(fact.segment ?? fact.scope_name)}</span>}
                      {fact.sentiment && <span className={`${sentimentClass(fact.sentiment)} text-[10px]`}>{displayToken(fact.sentiment)}</span>}
                    </div>
                  )}
                </article>
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function PresentationHighlights({ section }: { section: QuarterDocumentSection }) {
  const config = section.display ?? {};
  const metrics = selectMetrics(section.metrics, config.metric_priority, 4);
  const signals = rankDisplaySignals(section.signals, config);
  return (
    <div className="space-y-4">
      <DisplayMetricGrid metrics={metrics} title="Operating indicators" />
      <DisplayFactGroups section={section} groups={config.fact_groups ?? []} title="What drove it" maxItems={6} dedupeCodes />
      {signals.length > 0 && <EventSignalList signals={signals} title="Signals" />}
    </div>
  );
}

function isQuarterlyResultType(type: string | null | undefined) {
  const normalized = (type ?? "").toUpperCase().replace(/\s+/g, "_");
  return normalized === "FINANCIAL_RESULT" || normalized === "FINANCIAL_RESULTS" || normalized === "QUARTERLY_RESULT";
}

function isEarningsCallType(type: string | null | undefined) {
  const normalized = (type ?? "").toUpperCase().replace(/[\s-]+/g, "_");
  return normalized.includes("EARNINGS_CALL") || normalized.includes("CONCALL_TRANSCRIPT");
}

function cleanDimensionName(value: string | null | undefined) {
  if (!value) return "Company-wide";
  return displayToken(value).replace(/\bJio\b/g, "Jio").replace(/\bHpc\b/g, "HPC");
}

function EarningsCallAnalysis({ section }: { section: QuarterDocumentSection }) {
  const [supportingOpen, setSupportingOpen] = useState(false);
  const documentId = section.document?.id ?? section.event?.document_id ?? null;
  const config = section.display ?? {};
  const metrics = selectMetrics(section.metrics, config.metric_priority, 3);
  const signals = rankDisplaySignals(section.signals, config);

  return (
    <section className="space-y-4">
      <DisplayMetricGrid metrics={metrics} title="Forward indicators" />
      <DisplayFactGroups section={section} groups={config.fact_groups ?? []} title="Management read-through" maxItems={8} />
      {signals.length > 0 && <EventSignalList signals={signals} title="Signals" />}

      <section className="card overflow-hidden">
        <button type="button" onClick={() => setSupportingOpen((open) => !open)} aria-expanded={supportingOpen} className="focus-ring flex w-full items-center justify-between gap-4 rounded-2xl px-5 py-4 text-left hover:bg-surface-2/35"><span className="flex min-w-0 items-center gap-3"><FileSearch size={17} className="shrink-0 text-ink-soft" /><span><span className="block text-base font-semibold text-ink">Supporting transcript data</span><span className="mt-0.5 block text-xs text-ink-mute">Extracted claims and direct source references</span></span></span><ChevronDown size={16} className={clsx("shrink-0 text-ink-soft transition-transform", supportingOpen && "rotate-180")} /></button>
        {supportingOpen && <div className="border-t border-line/60 bg-bg/25 p-3 md:p-4"><FactsPanel facts={section.facts} factPeriods={section.fact_periods} activeFactPeriodEnd={section.selected_fact_period_end} fallbackDocumentId={documentId} /></div>}
      </section>
    </section>
  );
}

function QuarterlyResultAnalysis({ section, snapshot }: { section: QuarterDocumentSection; snapshot: SnapshotRow[] }) {
  const config = section.display ?? {};
  const allowedFacts = new Set(config.headline_facts ?? []);
  const headlineFacts = snapshot.filter((row) => allowedFacts.size === 0 || allowedFacts.has(row.code));
  const headlineMetrics = selectMetrics(
    section.metrics,
    config.headline_metrics,
    Math.max((config.max_headlines ?? 6) - headlineFacts.length, 0),
  );
  const signals = rankDisplaySignals(section.signals, config);

  return (
    <section className="space-y-4">
      {(headlineFacts.length > 0 || headlineMetrics.length > 0) && (
        <section className="card overflow-hidden">
          <div className="border-b border-line/60 px-5 py-4">
            <div className="flex items-center gap-2"><Sparkles size={16} className="text-brand-soft" /><h3 className="text-base font-semibold">Quarterly performance</h3></div>
            <p className="mt-1 text-xs text-ink-mute">Reported performance with prior-year comparison where available.</p>
          </div>
          <div className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-3">
            {headlineFacts.map((row) => <MetricCard key={row.code} label={row.metric} value={formatMetricValue(row.current_value, row.unit)} prior={row.previous_value != null ? formatMetricValue(row.previous_value, row.unit) : undefined} change={row.yoy_change_pct} />)}
            {headlineMetrics.map((metric) => <MetricCard key={metric.metric_code} label={metric.metric_name} value={formatMetricValue(metric.metric_value, metric.unit)} />)}
          </div>
        </section>
      )}

      {signals.length > 0 && <EventSignalList signals={signals} title="Signals" />}

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

function QuarterDocumentSectionPanel({ section, snapshot = [] }: { section: QuarterDocumentSection; snapshot?: SnapshotRow[] }) {
  const [supportingOpen, setSupportingOpen] = useState(false);
  const documentId = section.document?.id ?? section.event?.document_id ?? null;
  const sourceHref = documentId ? `/documents/${documentId}` : null;
  const eventDate = section.event?.event_date ?? section.document?.ingested_at ?? null;

  if (isQuarterlyResultType(section.document_type)) {
    return <QuarterlyResultAnalysis section={section} snapshot={snapshot} />;
  }

  if (isEarningsCallType(section.document_type)) {
    return <EarningsCallAnalysis section={section} />;
  }

  if (section.document_type === "INVESTOR_PRESENTATION") {
    return (
      <section className="space-y-4">
        <PresentationHighlights section={section} />
        <section className="card overflow-hidden">
          <button type="button" onClick={() => setSupportingOpen((open) => !open)} aria-expanded={supportingOpen} className="focus-ring flex w-full items-center justify-between gap-4 rounded-2xl px-5 py-4 text-left hover:bg-surface-2/35">
            <span className="flex min-w-0 items-center gap-3"><FileSearch size={17} className="shrink-0 text-ink-soft" /><span><span className="block text-base font-semibold text-ink">Supporting presentation data</span><span className="mt-0.5 block text-xs text-ink-mute">Extracted operating facts and direct source references</span></span></span>
            <ChevronDown size={16} className={clsx("shrink-0 text-ink-soft transition-transform", supportingOpen && "rotate-180")} />
          </button>
          {supportingOpen && <div className="border-t border-line/60 bg-bg/25 p-3 md:p-4"><FactsPanel facts={section.facts} factPeriods={section.fact_periods} activeFactPeriodEnd={section.selected_fact_period_end} fallbackDocumentId={documentId} /></div>}
        </section>
      </section>
    );
  }

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

function compactText(value: string, limit = 170): string {
  const normalized = value.replace(/\s+/g, " ").trim();
  return normalized.length > limit ? `${normalized.slice(0, limit - 1).trimEnd()}…` : normalized;
}

function quarterSectionSummary(section: QuarterDocumentSection, snapshot: SnapshotRow[]): string | null {
  const config = section.display ?? {};
  if (isQuarterlyResultType(section.document_type)) {
    const allowed = new Set(config.headline_facts ?? []);
    const rows = snapshot
      .filter((row) => allowed.size === 0 || allowed.has(row.code))
      .filter((row) => ["revenue_from_operations", "ebitda", "pat"].includes(row.code))
      .slice(0, 2);
    if (rows.length > 0) {
      return rows.map((row) => {
        const change = row.yoy_change_pct == null
          ? ""
          : ` (${row.yoy_change_pct > 0 ? "+" : ""}${row.yoy_change_pct.toFixed(1)}% YoY)`;
        return `${row.metric} ${formatMetricValue(row.current_value, row.unit)}${change}`;
      }).join(" · ");
    }
  }

  const displaySignals = rankDisplaySignals(section.signals, config);
  const guidanceGroup = config.fact_groups?.find((group) => group.key === "guidance");
  let preferredFact = guidanceGroup
    ? selectFactsForGroup(section.facts, guidanceGroup)[0]
    : config.fact_groups?.flatMap((group) => selectFactsForGroup(section.facts, group))[0];
  if (isEarningsCallType(section.document_type) && preferredFact) {
    const guidanceFacts = guidanceGroup ? selectFactsForGroup(section.facts, guidanceGroup) : [];
    const commitmentGroup = config.fact_groups?.find((group) => group.key === "commitments");
    const commitmentFacts = commitmentGroup ? selectFactsForGroup(section.facts, commitmentGroup) : [];
    preferredFact = guidanceFacts.find((fact) => fact.value_code !== "management_outlook")
      ?? commitmentFacts.find((fact) => fact.value_code === "management_commitment")
      ?? commitmentFacts[0]
      ?? preferredFact;
    return compactText(`${preferredFact.value_name}: ${factValueDisplay(preferredFact)}`);
  }
  if (displaySignals[0]) {
    return compactText(displaySignals[0].description || displaySignals[0].signal_name);
  }
  if (preferredFact) {
    return compactText(`${preferredFact.value_name}: ${factValueDisplay(preferredFact)}`);
  }
  return null;
}

function QuarterAtGlance({
  sections,
  snapshot,
  ticker,
  title = "Quarter at a glance",
  maxItems = 3,
  sourceOrder = ["FINANCIAL_RESULT", "INVESTOR_PRESENTATION", "EARNINGS_CALL_TRANSCRIPT"],
}: {
  sections: QuarterDocumentSection[];
  snapshot: SnapshotRow[];
  ticker: string;
  title?: string;
  maxItems?: number;
  sourceOrder?: string[];
}) {
  const rank = new Map(sourceOrder.map((type, index) => [type, index]));
  const items = sections
    .map((section) => ({ section, summary: quarterSectionSummary(section, snapshot) }))
    .filter((item): item is { section: QuarterDocumentSection; summary: string } => Boolean(item.summary))
    .sort((a, b) => (rank.get(a.section.document_type) ?? 99) - (rank.get(b.section.document_type) ?? 99))
    .slice(0, maxItems);
  if (items.length < 2) return null;

  return (
    <section className="card overflow-hidden">
      <div className="border-b border-line/60 px-5 py-4">
        <div className="flex items-center gap-2"><Sparkles size={16} className="text-brand-soft" /><h2 className="text-base font-semibold">{title}</h2></div>
        <p className="mt-1 text-xs text-ink-mute">Actual performance, operating evidence and management's forward view.</p>
      </div>
      <div className="grid gap-px bg-line/60 md:grid-cols-3">
        {items.map(({ section, summary }) => {
          const content = (
            <>
              <div className="text-[11px] font-semibold uppercase tracking-wider text-brand-soft">{section.display?.question ?? section.label}</div>
              <div className="mt-2 text-sm font-semibold text-ink">{section.label}</div>
              <p className="mt-1 text-sm leading-6 text-ink-mute">{summary}</p>
            </>
          );
          return section.event?.id && ticker ? (
            <Link key={section.key} to={`/company/${ticker}/event/${section.event.id}`} className="bg-surface p-4 transition-colors hover:bg-surface-2/55">{content}</Link>
          ) : (
            <div key={section.key} className="bg-surface p-4">{content}</div>
          );
        })}
      </div>
    </section>
  );
}

export function EventDetail() {
  const { ticker, eventId } = useParams<{ ticker: string; eventId: string }>();
  const [shareStatus, setShareStatus] = useState<"idle" | "shared" | "copied" | "error">("idle");

  const eventQuery = useQuery({
    queryKey: ["event", eventId],
    queryFn: () => api<EventDetailT>(`/events/${eventId}`),
    enabled: !!eventId,
    refetchInterval: (query) =>
      query.state.data?.intelligence_status?.state === "processing" ? 15_000 : false,
  });
  const { data, isLoading } = eventQuery;
  const generatedSummaryQuery = useQuery({
    queryKey: ["event-summary", eventId],
    queryFn: () =>
      api<EventSummary>(`/events/${eventId}/summary`, {
        method: "POST",
      }),
    enabled: Boolean(eventId && data && !data.event_summary),
    retry: 1,
    staleTime: Infinity,
  });

  if (isLoading) return <PageLoader />;
  if (!data) return <div className="text-ink-mute">Event not found.</div>;

  const { event, company, facts, metrics, signals } = data;
  const eventSummary = data.event_summary ?? generatedSummaryQuery.data ?? null;
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

  const shareFilingBrief = async () => {
    if (!eventSummary) return;

    const url = window.location.href;
    const companyName = company?.name || companyEventTicker || "Company";
    const title = `${companyName} AI filing brief`;
    const text = filingBriefShareText(eventSummary, companyName, event.period_label);

    try {
      if (navigator.share) {
        await navigator.share({ title, text, url });
        setShareStatus("shared");
      } else {
        await navigator.clipboard.writeText(`${text}\n\n${url}`);
        setShareStatus("copied");
      }
      window.setTimeout(() => setShareStatus("idle"), 2_500);
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      try {
        await navigator.clipboard.writeText(`${text}\n\n${url}`);
        setShareStatus("copied");
        window.setTimeout(() => setShareStatus("idle"), 2_500);
      } catch {
        setShareStatus("error");
      }
    }
  };

  return (
    <div className="w-full min-w-0 max-w-4xl mx-auto space-y-6 overflow-hidden">
      <BackButton fallback={ticker ? `/company/${ticker}` : "/companies"} />

      <header className="card p-5 md:p-6 space-y-3">
        <div className="flex items-center justify-between gap-3">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-soft">
            {eventTypeLabel(event.event_type)}
          </span>
          {event.period_label && <span className="chip-neutral">{event.period_label}</span>}
        </div>
        <h1 className="text-xl md:text-2xl font-semibold text-ink leading-snug">
          {company?.name}
          {event.period_label && (
            <span className="text-ink-mute font-normal"> · {event.period_label}</span>
          )}
        </h1>
        <div className="text-sm text-ink-soft">{formatDate(event.event_date)}</div>
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line/50 pt-3">
        {relatedDocumentEvents.length > 1 ? (
          <nav className="flex min-w-0 flex-wrap items-center gap-2" aria-label="Quarter documents">
            {relatedDocumentEvents.map((item) => (
              <Link
                key={item.id}
                to={`/company/${companyEventTicker}/event/${item.id}`}
                className={clsx("focus-ring inline-flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm transition-colors", item.id === event.id ? "bg-surface-3 text-ink" : "text-ink-mute hover:bg-surface-2 hover:text-ink")}
              >
                <FileText size={14} />
                {resolveEventDisplayTitle(item.event_type, item.title)}
              </Link>
            ))}
          </nav>
        ) : <span />}
        {event.document_id ? (
          <Link
            to={`/documents/${event.document_id}`}
            className="btn-primary shrink-0"
          >
            <FileText size={15} /> {isQuarterlyResultType(event.event_type) ? "Open filing" : event.event_type === "INVESTOR_PRESENTATION" ? "Open presentation" : isEarningsCallType(event.event_type) ? "Open transcript" : "Open document"} <ArrowUpRight size={14} />
          </Link>
        ) : null}
        </div>
      </header>

      {eventSummary ? (
        <section className="card overflow-hidden border-brand/20" aria-label="AI filing brief">
          <div className="border-b border-line/60 bg-brand/5 px-5 py-4 md:px-6">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-brand-soft">
                <Sparkles size={16} />
                <span className="text-[11px] font-semibold uppercase tracking-[0.12em]">
                  AI filing brief
                </span>
              </div>
              <div className="flex flex-wrap items-center justify-end gap-2">
                <span className="chip-neutral text-[10px]">Grounded in filing markdown</span>
                <button
                  type="button"
                  className="btn-secondary px-2.5 py-1.5 text-xs"
                  onClick={() => void shareFilingBrief()}
                  aria-label="Share AI filing brief"
                >
                  {shareStatus === "shared" || shareStatus === "copied" ? (
                    <Check size={14} />
                  ) : (
                    <Share2 size={14} />
                  )}
                  {shareStatus === "shared"
                    ? "Shared"
                    : shareStatus === "copied"
                      ? "Copied"
                      : shareStatus === "error"
                        ? "Unable to share"
                        : "Share"}
                </button>
              </div>
            </div>
            <h2 className="mt-3 text-lg font-semibold leading-snug text-ink md:text-xl">
              {eventSummary.headline}
            </h2>
            <p className="mt-2 text-sm leading-6 text-ink-mute">{eventSummary.summary}</p>
          </div>

          <div className="space-y-4 p-5 md:p-6">
            <ul className="grid gap-3 md:grid-cols-3">
              {eventSummary.key_points.map((point, index) => (
                <li key={`${index}-${point}`} className="rounded-xl border border-line/70 bg-surface-2/45 p-3.5">
                  <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-ink-soft">
                    Key point {index + 1}
                  </div>
                  <p className="text-sm leading-6 text-ink">{point}</p>
                </li>
              ))}
            </ul>
            <div className="rounded-xl border border-brand/20 bg-brand/5 px-4 py-3.5">
              <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-brand-soft">
                Investor takeaway
              </div>
              <p className="mt-1.5 text-sm font-medium leading-6 text-ink">
                {eventSummary.investor_takeaway}
              </p>
            </div>
            <p className="text-[10px] leading-relaxed text-ink-soft">
              AI-generated from the parsed source filing. Review the linked filing before making decisions.
            </p>
          </div>
        </section>
      ) : generatedSummaryQuery.isLoading ? (
        <section className="card px-5 py-4" role="status">
          <div className="flex items-center gap-3">
            <Loader2 className="shrink-0 animate-spin text-brand" size={17} />
            <div>
              <div className="text-sm font-semibold text-ink">Preparing the filing brief</div>
              <p className="mt-0.5 text-xs text-ink-mute">
                Reading the filing and identifying the most material developments.
              </p>
            </div>
          </div>
        </section>
      ) : generatedSummaryQuery.isError ? (
        <section className="rounded-2xl border border-line bg-surface px-5 py-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-ink-mute">The AI filing brief is temporarily unavailable.</p>
            <button type="button" className="btn-secondary text-xs" onClick={() => generatedSummaryQuery.refetch()}>
              Try again
            </button>
          </div>
        </section>
      ) : null}

      {data.intelligence_status?.state === "processing" && (
        <section className="rounded-2xl border border-brand/25 bg-brand/5 px-5 py-4" role="status">
          <div className="flex items-start gap-3">
            <Loader2 className="mt-0.5 shrink-0 animate-spin text-brand" size={18} />
            <div>
              <h2 className="text-sm font-semibold text-ink">Signals processing</h2>
              <p className="mt-1 text-sm leading-6 text-ink-mute">
                Some extracted facts are being verified. Current signals use verified facts and
                will refresh automatically when verification finishes. You can return to
                this update later.
              </p>
            </div>
          </div>
        </section>
      )}

      <QuarterAtGlance
        sections={allDocumentSections}
        snapshot={data.financial_snapshot}
        ticker={companyEventTicker}
        title={data.quarter_display?.title ?? undefined}
        maxItems={data.quarter_display?.max_items ?? undefined}
        sourceOrder={data.quarter_display?.source_order ?? undefined}
      />

      {documentSections.length > 0 ? (
        <div className="space-y-8">
          {documentSections.map((section) => (
            <QuarterDocumentSectionPanel key={section.key} section={section} snapshot={section.event?.id === event.id ? data.financial_snapshot : []} />
          ))}
        </div>
      ) : (
        <Empty title="No document categories" description="No processed documents were found for this quarter." />
      )}
    </div>
  );
}
