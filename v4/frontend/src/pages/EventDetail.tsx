import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, BarChart3, ChevronDown, FileSearch, FileText, Layers3, MessageSquareQuote, Sparkles, Target, TrendingDown, TrendingUp } from "lucide-react";
import clsx from "clsx";
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
import { MetricCard } from "@/components/common/DashboardUI";
import type { SnapshotRow } from "@/api/types";

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
              <h3 className="text-base font-semibold">Presentation coverage</h3>
              <p className="text-xs text-ink-soft mt-0.5">
                Business areas and themes identified in the source material.
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="chip-neutral">{segmentCount} segments</span>
            <span className="chip-neutral">{summary.guidance_count} guidance facts</span>
            {confidencePct != null && <span className="chip-neutral">{confidencePct}% extraction confidence</span>}
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
                  {displayToken(segment.name).replace(/\bT D\b/g, "T&D").replace(/\bNon T D\b/g, "Non-T&D")}
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

const PRESENTATION_FINANCIAL_CODES = ["revenue", "ebitda", "ebitda_margin", "pat", "order_book", "order_inflow"];

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

function PresentationHighlights({ section }: { section: QuarterDocumentSection }) {
  const financials = uniquePresentationFacts(section.facts.filter((fact) =>
    !fact.segment && PRESENTATION_FINANCIAL_CODES.some((code) => fact.value_code.toLowerCase().includes(code)),
  )).slice(0, 8);
  const segmentFacts = uniquePresentationFacts(section.facts.filter((fact) =>
    Boolean(fact.segment) && !/^fy\s?\d+/i.test(fact.segment ?? "") && ["segment_revenue", "segment_growth_yoy", "order_book", "order_inflow"].some((code) => fact.value_code.toLowerCase().includes(code)),
  ));
  const highlightFacts = uniquePresentationFacts([
    ...section.facts.filter((fact) => fact.is_explicit_guidance),
    ...section.facts.filter((fact) => fact.category === "order_book_pipeline" && !/^fy\s?\d+/i.test(fact.segment ?? "")),
    ...section.facts.filter((fact) => fact.category === "capex_capacity"),
    ...section.facts.filter((fact) => fact.category === "financial_highlight"),
  ]).slice(0, 6);

  return (
    <div className="space-y-4">
      {highlightFacts.length > 0 && (
        <section className="card overflow-hidden">
          <div className="border-b border-line/60 px-5 py-4">
            <div className="flex items-center gap-2"><Sparkles size={16} className="text-brand-soft" /><h3 className="text-base font-semibold">Presentation highlights</h3></div>
            <p className="mt-1 text-xs text-ink-mute">The most decision-relevant reported facts from this presentation.</p>
          </div>
          <div className="grid gap-px bg-line/60 sm:grid-cols-2 lg:grid-cols-3">
            {highlightFacts.map((fact) => (
              <div key={`${fact.value_code}-${fact.value_numeric}-${fact.segment ?? "company"}`} className="bg-surface p-4">
                <div className="flex items-start justify-between gap-3"><span className="text-xs font-medium text-ink-mute">{cleanFactName(fact.value_name)}</span><Target size={14} className="shrink-0 text-ink-soft" /></div>
                <div className="mt-2 text-xl font-semibold tracking-tight text-ink num">{factValueDisplay(fact)}</div>
                <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[11px] text-ink-soft">
                  <span>{presentationContext(fact)}</span>{fact.segment && <span>· {displayToken(fact.segment)}</span>}
                  <FactSourceLink documentId={fact.document_id ?? section.document?.id ?? null} fact={fact} />
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {financials.length > 0 && (
        <section className="card overflow-hidden">
          <div className="border-b border-line/60 px-5 py-4"><div className="flex items-center gap-2"><BarChart3 size={16} className="text-brand-soft" /><h3 className="text-base font-semibold">Financial highlights</h3></div></div>
          <div className="divide-y divide-line/40 sm:hidden">
            {financials.map((fact) => <div key={`mobile-${fact.value_code}-${fact.value_numeric}-${presentationContext(fact)}`} className="flex items-start justify-between gap-4 px-4 py-3"><div className="min-w-0"><div className="text-sm font-medium text-ink">{cleanFactName(fact.value_name)}</div><div className="mt-1 text-xs text-ink-mute">{presentationContext(fact)}</div></div><div className="shrink-0 text-right"><div className="font-semibold text-ink num">{factValueDisplay(fact)}</div><div className="mt-1"><FactSourceLink documentId={fact.document_id ?? section.document?.id ?? null} fact={fact} /></div></div></div>)}
          </div>
          <div className="hidden max-w-full overflow-x-auto sm:block">
            <table className="w-full min-w-[34rem] text-sm">
              <thead className="text-[11px] uppercase tracking-wider text-ink-soft"><tr><th className="px-5 py-2 text-left font-medium">Metric</th><th className="px-5 py-2 text-left font-medium">Period</th><th className="px-5 py-2 text-right font-medium">Value</th><th className="w-20 px-5 py-2 text-center font-medium">Source</th></tr></thead>
              <tbody>{financials.map((fact) => <tr key={`${fact.value_code}-${fact.value_numeric}-${presentationContext(fact)}`} className="border-t border-line/40"><td className="px-5 py-3 font-medium text-ink">{cleanFactName(fact.value_name)}</td><td className="px-5 py-3 text-ink-mute">{presentationContext(fact)}</td><td className="px-5 py-3 text-right font-semibold text-ink num">{factValueDisplay(fact)}</td><td className="px-5 py-3 text-center"><FactSourceLink documentId={fact.document_id ?? section.document?.id ?? null} fact={fact} /></td></tr>)}</tbody>
            </table>
          </div>
        </section>
      )}

      {segmentFacts.length > 0 && (
        <section className="card overflow-hidden">
          <div className="border-b border-line/60 px-5 py-4"><h3 className="text-base font-semibold">Segment performance</h3><p className="mt-1 text-xs text-ink-mute">Reported revenue, growth, and order activity by business area.</p></div>
          <div className="grid gap-px bg-line/60 sm:grid-cols-2 lg:grid-cols-3">
            {segmentFacts.slice(0, 12).map((fact) => <div key={`${fact.value_code}-${fact.segment}-${fact.value_numeric}-${presentationContext(fact)}`} className="bg-surface p-4"><div className="text-[11px] font-semibold uppercase tracking-wider text-brand-soft">{displayToken(fact.segment).replace(/\bT D\b/g, "T&D")}</div><div className="mt-2 text-sm font-medium text-ink-mute">{cleanFactName(fact.value_name)}</div><div className="mt-1 text-lg font-semibold text-ink num">{factValueDisplay(fact)}</div><div className="mt-2 text-xs text-ink-soft">{presentationContext(fact)}</div></div>)}
          </div>
        </section>
      )}
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
  const uniqueFacts = uniquePresentationFacts(section.facts);
  const guidance = uniqueFacts.filter((fact) => Boolean(fact.is_explicit_guidance));
  const positive = uniqueFacts.filter((fact) => fact.sentiment?.toLowerCase() === "positive");
  const negative = uniqueFacts.filter((fact) => fact.sentiment?.toLowerCase() === "negative");
  const neutral = uniqueFacts.filter((fact) => !fact.sentiment || ["neutral", "mixed"].includes(fact.sentiment.toLowerCase()));
  const takeaways = [...guidance, ...negative, ...positive, ...neutral].filter((fact, index, rows) => rows.findIndex((item) => item.value_text === fact.value_text && item.segment === fact.segment) === index).slice(0, 6);
  const segmentGroups = new Map<string, ExtractedValue[]>();
  uniqueFacts.filter((fact) => fact.segment).forEach((fact) => {
    const key = fact.segment ?? "company";
    const rows = segmentGroups.get(key) ?? [];
    if (rows.length < 2) rows.push(fact);
    segmentGroups.set(key, rows);
  });

  return (
    <section className="space-y-4">
      <section className="grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-line bg-line lg:grid-cols-4" aria-label="Management commentary summary">
        {[
          { label: "Commentary facts", value: uniqueFacts.length, icon: MessageSquareQuote, tone: "text-ink" },
          { label: "Positive", value: positive.length, icon: TrendingUp, tone: "text-positive" },
          { label: "Watch items", value: negative.length, icon: TrendingDown, tone: negative.length ? "text-negative" : "text-ink" },
          { label: "Guidance", value: guidance.length, icon: Target, tone: guidance.length ? "text-brand-soft" : "text-ink" },
        ].map((item) => <div key={item.label} className="bg-surface px-4 py-4"><div className="flex items-center justify-between gap-2 text-[11px] font-medium uppercase tracking-wider text-ink-soft"><span>{item.label}</span><item.icon size={14} /></div><div className={clsx("mt-2 text-2xl font-semibold num", item.tone)}>{item.value}</div></div>)}
      </section>

      {takeaways.length > 0 && (
        <section className="card overflow-hidden">
          <div className="border-b border-line/60 px-5 py-4"><div className="flex items-center gap-2"><Sparkles size={16} className="text-brand-soft" /><h3 className="text-base font-semibold">Management takeaways</h3></div><p className="mt-1 text-xs text-ink-mute">Key operating and financial commentary from management.</p></div>
          <div className="grid gap-px bg-line/60 md:grid-cols-2">
            {takeaways.map((fact) => {
              const sentiment = fact.sentiment?.toLowerCase();
              return <article key={`${fact.value_code}-${fact.segment}-${fact.value_text}`} className="bg-surface p-4"><div className="flex items-center justify-between gap-3"><span className="text-[11px] font-semibold uppercase tracking-wider text-brand-soft">{cleanDimensionName(fact.segment ?? fact.scope_name)}</span><span className={sentimentClass(fact.sentiment)}>{displayToken(sentiment ?? "neutral")}</span></div><blockquote className="mt-3 text-sm font-medium leading-6 text-ink">“{fact.value_text || factValueDisplay(fact)}”</blockquote><div className="mt-3 flex items-center justify-between gap-3 text-xs text-ink-soft"><span>{displayToken(fact.metric_context ?? fact.fact_type)}</span><FactSourceLink documentId={fact.document_id ?? documentId} fact={fact} /></div></article>;
            })}
          </div>
        </section>
      )}

      {guidance.length > 0 && (
        <section className="card overflow-hidden"><div className="border-b border-line/60 px-5 py-4"><div className="flex items-center gap-2"><Target size={16} className="text-brand-soft" /><h3 className="text-base font-semibold">Guidance and outlook</h3></div></div><div className="divide-y divide-line/40">{guidance.slice(0, 8).map((fact) => <div key={`${fact.value_code}-${fact.value_text}`} className="flex items-start justify-between gap-4 px-5 py-4"><div><div className="text-xs font-semibold uppercase tracking-wider text-brand-soft">{cleanDimensionName(fact.segment)}</div><p className="mt-1 text-sm leading-6 text-ink">{fact.value_text || factValueDisplay(fact)}</p></div><FactSourceLink documentId={fact.document_id ?? documentId} fact={fact} /></div>)}</div></section>
      )}

      {segmentGroups.size > 0 && (
        <section className="card overflow-hidden">
          <div className="border-b border-line/60 px-5 py-4"><h3 className="text-base font-semibold">Business commentary</h3><p className="mt-1 text-xs text-ink-mute">Management commentary organised by business or operating theme.</p></div>
          <div className="grid gap-px bg-line/60 sm:grid-cols-2 lg:grid-cols-3">{[...segmentGroups.entries()].slice(0, 9).map(([segment, facts]) => <div key={segment} className="bg-surface p-4"><div className="text-[11px] font-semibold uppercase tracking-wider text-brand-soft">{cleanDimensionName(segment)}</div><div className="mt-3 space-y-3">{facts.map((fact) => <div key={`${fact.value_code}-${fact.value_text}`}><p className="text-sm leading-5 text-ink">{fact.value_text || factValueDisplay(fact)}</p><div className="mt-1 text-xs text-ink-soft">{displayToken(fact.metric_context)}</div></div>)}</div></div>)}</div>
        </section>
      )}

      {section.signals.length > 0 && <EventSignalList signals={section.signals} title="Material signals" />}

      <section className="card overflow-hidden">
        <button type="button" onClick={() => setSupportingOpen((open) => !open)} aria-expanded={supportingOpen} className="focus-ring flex w-full items-center justify-between gap-4 rounded-2xl px-5 py-4 text-left hover:bg-surface-2/35"><span className="flex min-w-0 items-center gap-3"><FileSearch size={17} className="shrink-0 text-ink-soft" /><span><span className="block text-base font-semibold text-ink">Supporting transcript data</span><span className="mt-0.5 block text-xs text-ink-mute">{section.counts.facts} extracted commentary facts and transcript references</span></span></span><ChevronDown size={16} className={clsx("shrink-0 text-ink-soft transition-transform", supportingOpen && "rotate-180")} /></button>
        {supportingOpen && <div className="border-t border-line/60 bg-bg/25 p-3 md:p-4"><FactsPanel facts={section.facts} factPeriods={section.fact_periods} activeFactPeriodEnd={section.selected_fact_period_end} fallbackDocumentId={documentId} /></div>}
      </section>
    </section>
  );
}

function QuarterlyResultAnalysis({ section, snapshot }: { section: QuarterDocumentSection; snapshot: SnapshotRow[] }) {
  const [supportingOpen, setSupportingOpen] = useState(false);
  const documentId = section.document?.id ?? section.event?.document_id ?? null;
  const ratioMetrics = section.metrics.filter((metric) => metric.metric_value != null).slice(0, 9);

  return (
    <section className="space-y-4">
      {snapshot.length > 0 && (
        <section className="card overflow-hidden">
          <div className="border-b border-line/60 px-5 py-4">
            <div className="flex items-center gap-2"><Sparkles size={16} className="text-brand-soft" /><h3 className="text-base font-semibold">Quarterly performance</h3></div>
            <p className="mt-1 text-xs text-ink-mute">Reported performance with prior-year comparison where available.</p>
          </div>
          <div className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-3">
            {snapshot.slice(0, 9).map((row) => <MetricCard key={row.code} label={row.metric} value={formatMetricValue(row.current_value, row.unit)} prior={row.previous_value != null ? formatMetricValue(row.previous_value, row.unit) : undefined} change={row.yoy_change_pct} />)}
          </div>
        </section>
      )}

      {section.signals.length > 0 && <EventSignalList signals={section.signals} title="Material signals" />}

      {ratioMetrics.length > 0 && (
        <section className="card overflow-hidden">
          <div className="border-b border-line/60 px-5 py-4"><div className="flex items-center gap-2"><BarChart3 size={16} className="text-brand-soft" /><h3 className="text-base font-semibold">Margins and financial indicators</h3></div><p className="mt-1 text-xs text-ink-mute">Derived indicators calculated from the reported financial statements.</p></div>
          <div className="grid gap-px bg-line/60 sm:grid-cols-2 lg:grid-cols-3">
            {ratioMetrics.map((metric) => <div key={metric.metric_code} className="bg-surface p-4"><div className="flex items-start justify-between gap-2"><span className="text-xs font-medium text-ink-mute">{metric.metric_name}</span><MetricFormulaInfo calculationData={metric.calculation_data} metricName={metric.metric_name} /></div><div className="mt-2 text-xl font-semibold tracking-tight text-ink num">{formatMetricValue(metric.metric_value, metric.unit)}</div><div className="mt-2 text-[11px] uppercase tracking-wider text-ink-soft">{categoryGroupLabel(metric.category)}</div></div>)}
          </div>
        </section>
      )}

      <section className="card overflow-hidden">
        <button type="button" onClick={() => setSupportingOpen((open) => !open)} aria-expanded={supportingOpen} className="focus-ring flex w-full items-center justify-between gap-4 rounded-2xl px-5 py-4 text-left hover:bg-surface-2/35">
          <span className="flex min-w-0 items-center gap-3"><FileSearch size={17} className="shrink-0 text-ink-soft" /><span><span className="block text-base font-semibold text-ink">Supporting financial data</span><span className="mt-0.5 block text-xs text-ink-mute">{section.counts.facts} statement line items and source references</span></span></span>
          <ChevronDown size={16} className={clsx("shrink-0 text-ink-soft transition-transform", supportingOpen && "rotate-180")} />
        </button>
        {supportingOpen && <div className="border-t border-line/60 bg-bg/25 p-3 md:p-4"><FactsPanel facts={section.facts} factPeriods={section.fact_periods} activeFactPeriodEnd={section.selected_fact_period_end} fallbackDocumentId={documentId} /></div>}
      </section>
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
        {section.signals.length > 0 && <EventSignalList signals={section.signals} title="Material signals" />}
        {section.metrics.length > 0 && <MetricsPanel metrics={section.metrics} />}
        <section className="card overflow-hidden">
          <button type="button" onClick={() => setSupportingOpen((open) => !open)} aria-expanded={supportingOpen} className="focus-ring flex w-full items-center justify-between gap-4 rounded-2xl px-5 py-4 text-left hover:bg-surface-2/35">
            <span className="flex min-w-0 items-center gap-3"><FileSearch size={17} className="shrink-0 text-ink-soft" /><span><span className="block text-base font-semibold text-ink">Supporting data</span><span className="mt-0.5 block text-xs text-ink-mute">{section.counts.facts} extracted facts, presentation coverage, and extraction quality</span></span></span>
            <ChevronDown size={16} className={clsx("shrink-0 text-ink-soft transition-transform", supportingOpen && "rotate-180")} />
          </button>
          {supportingOpen && <div className="space-y-4 border-t border-line/60 bg-bg/25 p-3 md:p-4"><PresentationSummaryPanel section={section} /><FactsPanel facts={section.facts} factPeriods={section.fact_periods} activeFactPeriodEnd={section.selected_fact_period_end} fallbackDocumentId={documentId} /></div>}
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

export function EventDetail() {
  const { ticker, eventId } = useParams<{ ticker: string; eventId: string }>();

  const eventQuery = useQuery({
    queryKey: ["event", eventId],
    queryFn: () => api<EventDetailT>(`/events/${eventId}`),
    enabled: !!eventId,
  });
  const { data, isLoading } = eventQuery;

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
