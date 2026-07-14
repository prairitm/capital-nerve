import type { DocumentDisplayConfig, MetricValue, Signal } from "@/api/types";
import { formatMetricValue } from "@/lib/format";

const CATEGORY_LABELS: Record<string, string> = {
  growth: "Growth",
  margin: "Margin",
  profit_quality: "Profit Quality",
  earnings_quality: "Earnings Quality",
  cash_quality: "Cash Quality",
  expense: "Expense",
  debt: "Debt",
  management: "Management",
  red_flag: "Red Flag",
};

export function signalCategoryLabel(category: string | null | undefined): string {
  if (!category) return "Signal";
  return (
    CATEGORY_LABELS[category] ||
    category.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
  );
}

const SEVERITY_RANK: Record<string, number> = {
  CRITICAL: 0,
  HIGH: 1,
  MEDIUM: 2,
  LOW: 3,
};

/** Select the small, non-duplicative signal set declared for a document type. */
export function rankDisplaySignals(
  signals: Signal[],
  config: DocumentDisplayConfig | null | undefined,
): Signal[] {
  const priority = config?.signal_priority ?? [];
  const maxSignals = config?.max_signals ?? 3;
  const allowed = new Set(priority);
  const priorityRank = new Map(priority.map((code, index) => [code, index]));
  const groups = config?.signal_groups ?? {};
  const candidates = priority.length > 0
    ? signals.filter((signal) => allowed.has(signal.signal_type))
    : [...signals];

  candidates.sort((a, b) => {
    const priorityDifference =
      (priorityRank.get(a.signal_type) ?? Number.MAX_SAFE_INTEGER) -
      (priorityRank.get(b.signal_type) ?? Number.MAX_SAFE_INTEGER);
    if (priorityDifference !== 0) return priorityDifference;
    return (
      (SEVERITY_RANK[a.severity ?? ""] ?? 9) -
      (SEVERITY_RANK[b.severity ?? ""] ?? 9)
    );
  });

  const selected: Signal[] = [];
  const seenGroups = new Set<string>();
  for (const signal of candidates) {
    const group = groups[signal.signal_type] ?? signal.signal_type;
    if (seenGroups.has(group)) continue;
    seenGroups.add(group);
    selected.push(signal);
    if (selected.length >= maxSignals) break;
  }
  return selected;
}

export interface FeedRow {
  id: string;
  headline: string;
  summary: string | null;
  direction: Signal["direction"];
  severity: Signal["severity"];
  categoryLabel: string;
  companyName: string | null;
  companyTicker: string | null;
  triggerValues: Record<string, number>;
  detectedAt: string | null;
  eventId: string | null;
}

export function metricCodeLabel(code: string, metrics: MetricValue[] = []): string {
  const found = metrics.find((m) => m.metric_code === code);
  if (found?.metric_name) return found.metric_name;
  return code.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function humanizeRuleText(rule: string, metrics: MetricValue[] = []): string {
  let text = rule;
  for (const m of metrics) {
    text = text.split(m.metric_code).join(m.metric_name);
  }
  return text;
}

function operatorVerb(op: string): string {
  switch (op) {
    case ">":
      return "exceeded";
    case ">=":
      return "met or exceeded";
    case "<":
      return "fell below";
    case "<=":
      return "was at or below";
    case "==":
      return "equaled";
    case "!=":
      return "did not equal";
    default:
      return op;
  }
}

/** Parse a single-metric leaf rule like `cfo_to_pat > 1.0`. */
function parseSimpleRule(
  rule: string,
): { metricCode: string; operator: string; threshold: number } | null {
  const match = /^(\w+)\s*(>=|<=|==|!=|[<>])\s*([\d.]+)$/.exec(rule.trim());
  if (!match) return null;
  return { metricCode: match[1], operator: match[2], threshold: Number(match[3]) };
}

/** One-line explanation for simple threshold rules on the signal detail page. */
export function buildTriggerNarrative(
  ruleText: string | null | undefined,
  triggerValues: Record<string, number>,
  metrics: MetricValue[] = [],
): string | null {
  if (!ruleText) return null;

  const parsed = parseSimpleRule(ruleText);
  if (!parsed) return null;

  const label = metricCodeLabel(parsed.metricCode, metrics);
  const metric = metrics.find((m) => m.metric_code === parsed.metricCode);
  const unit = metric?.unit ?? null;
  const observed = triggerValues[parsed.metricCode] ?? metric?.metric_value ?? null;
  if (observed === null || observed === undefined || Number.isNaN(observed)) return null;

  const observedStr = formatMetricValue(observed, unit);
  const thresholdStr = formatMetricValue(parsed.threshold, unit);
  return `${label} was ${observedStr}, which ${operatorVerb(parsed.operator)} the threshold of ${thresholdStr}.`;
}

export interface TriggerMetricRow {
  code: string;
  name: string;
  value: number | null;
  unit: string | null;
  calculationData?: MetricValue["calculation_data"] | null;
}

/** Unified metric rows for signal detail — referenced metrics plus orphan trigger values. */
export function buildTriggerMetricRows(
  triggerValues: Record<string, number>,
  metrics: MetricValue[] = [],
): TriggerMetricRow[] {
  const covered = new Set(metrics.map((m) => m.metric_code));
  const rows: TriggerMetricRow[] = metrics.map((m) => ({
    code: m.metric_code,
    name: m.metric_name,
    value: m.metric_value,
    unit: m.unit,
    calculationData: m.calculation_data,
  }));

  for (const [code, value] of Object.entries(triggerValues)) {
    if (covered.has(code)) continue;
    rows.push({
      code,
      name: metricCodeLabel(code, metrics),
      value,
      unit: null,
      calculationData: null,
    });
  }

  return rows;
}

/** Adapt a backend Signal into the narrow shape the feed/signal cards render. */
export function signalToFeedRow(s: Signal): FeedRow {
  return {
    id: s.id,
    headline: s.signal_name || s.title || s.signal_type,
    summary: s.description,
    direction: s.direction,
    severity: s.severity,
    categoryLabel: signalCategoryLabel(s.category),
    companyName: s.company?.name ?? null,
    companyTicker: s.company?.ticker ?? null,
    triggerValues: s.evidence?.trigger_values ?? {},
    detectedAt: s.detected_at,
    eventId: s.event_id,
  };
}
