import type { SignalDirection } from "@/api/types";

export function formatNumber(n: number | null | undefined, fractionDigits = 0): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return Number(n).toLocaleString("en-IN", {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  });
}

export function formatSigned(n: number | null | undefined, fractionDigits = 1, suffix = ""): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const sign = n > 0 ? "+" : n < 0 ? "" : "";
  return `${sign}${Number(n).toFixed(fractionDigits)}${suffix}`;
}

export function formatCr(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (Math.abs(value) >= 100000) return `${(value / 100000).toFixed(2)} L Cr`;
  return `${formatNumber(value, value < 100 ? 1 : 0)} Cr`;
}

export function formatPct(value: number | null | undefined, fractionDigits = 1): string {
  if (value === null || value === undefined) return "—";
  return `${value.toFixed(fractionDigits)}%`;
}

/**
 * Confidence scores are stored as `Numeric(5, 2)` on the backend (0–100 scale)
 * across `extracted_values`, `financial_statement_facts`, `calculated_metrics`,
 * `generated_signals`, and `intelligence_cards`. A defensive heuristic accepts
 * legacy 0–1 fractions so the same helper can be used on every surface.
 */
export function normalizeConfidenceScore(score: number | null | undefined): number | null {
  if (score == null || Number.isNaN(score)) return null;
  return score <= 1.5 ? score * 100 : score;
}

export function formatExtractionConfidence(
  score: number | null | undefined,
  fractionDigits = 0,
): string {
  const v = normalizeConfidenceScore(score);
  if (v == null) return "—";
  return `${v.toFixed(fractionDigits)}%`;
}

export function confidenceTone(score: number | null | undefined): string {
  const v = normalizeConfidenceScore(score);
  if (v == null) return "text-ink-soft";
  if (v >= 85) return "text-positive";
  if (v >= 60) return "text-ink";
  return "text-ink-mute";
}

/** YoY column on financial snapshot tables (relative % or margin bps). */
export function formatSnapshotYoY(
  row: {
    yoy_change_bps?: number | null;
    yoy_change_pct?: number | null;
  },
): string {
  if (row.yoy_change_bps != null) return formatSigned(row.yoy_change_bps, 0, " bps");
  if (row.yoy_change_pct != null) return formatSigned(row.yoy_change_pct, 1, "%");
  return "—";
}

export function snapshotYoYIsPositive(row: {
  yoy_change_bps?: number | null;
  yoy_change_pct?: number | null;
}): boolean | null {
  if (row.yoy_change_bps != null) return row.yoy_change_bps > 0;
  if (row.yoy_change_pct != null) return row.yoy_change_pct > 0;
  return null;
}

/**
 * Evidence values are stored as text. Pre-formatted document copy (Rs, %, Cr, commas)
 * is returned unchanged; raw floats like `37146.000000` are shown without noise.
 */
export function formatEvidenceValue(value: string | null | undefined): string | null {
  if (value == null) return null;
  const trimmed = value.trim();
  if (!trimmed) return null;

  if (
    /[%,₹$]/.test(trimmed) ||
    /\b(Rs|INR|Cr|crore|Lakh|Lac|bps)\b/i.test(trimmed) ||
    /\(\d/.test(trimmed) ||
    /,\d{2,3}(?:,\d{3})+/.test(trimmed)
  ) {
    return trimmed;
  }

  const normalized = trimmed.replace(/,/g, "");
  if (!/^-?\d+(\.\d+)?$/.test(normalized)) {
    return trimmed;
  }

  const n = Number(normalized);
  if (!Number.isFinite(n)) return trimmed;

  const fracPart = normalized.split(".")[1];
  if (!fracPart || /^0+$/.test(fracPart)) {
    return formatNumber(n, 0);
  }

  const significantDecimals = fracPart.replace(/0+$/, "").length;
  return formatNumber(n, Math.min(4, Math.max(1, significantDecimals)));
}

export type EvidenceHighlightInput = {
  evidence_value: string | null;
  source_text: string | null;
};

/** One row in the document evidence panel (subset of `DocumentDetail.evidence`). */
export type PageEvidenceRow = {
  card_evidence_id: number;
  evidence_type?: string | null;
  evidence_label: string | null;
  evidence_value: string | null;
  source_text: string | null;
  calculation_text: string | null;
  confidence_score: number | null;
};

function factDedupeKey(row: PageEvidenceRow): string {
  const label = (row.evidence_label ?? "").trim().toLowerCase();
  const value = (row.evidence_value ?? "").trim().toLowerCase();
  if (!label && !value) return `row:${row.card_evidence_id}`;
  return `${label}\x00${value}`;
}

function evidenceRowRank(row: PageEvidenceRow): number {
  let rank = row.confidence_score ?? 0;
  if (row.source_text?.trim()) rank += 100;
  const t = row.evidence_type ?? "";
  if (t === "source_quote" || t === "extracted_value") rank += 50;
  if (t === "calculated_metric") rank -= 40;
  if (row.calculation_text?.trim()) rank += 10;
  return rank;
}

/** One panel row per distinct label+value (cards, supplemental, and calculated_metric duplicates). */
export function dedupePageEvidenceRows(rows: PageEvidenceRow[]): PageEvidenceRow[] {
  const order: string[] = [];
  const best = new Map<string, PageEvidenceRow>();

  for (const row of rows) {
    const key = factDedupeKey(row);
    const prev = best.get(key);
    if (!prev) {
      best.set(key, row);
      order.push(key);
      continue;
    }
    if (evidenceRowRank(row) > evidenceRowRank(prev)) {
      best.set(key, row);
    }
  }

  return order.map((k) => best.get(k)!);
}

/** Evidence rows that share the same `source_text` on a page, shown as one card. */
export type GroupedPageEvidence = {
  groupKey: string;
  sourceText: string | null;
  items: PageEvidenceRow[];
};

/** Collapse duplicate source quotes on the active page (e.g. EBITDA + margin from one sentence). */
export function groupEvidenceBySourceText(rows: PageEvidenceRow[]): GroupedPageEvidence[] {
  const order: string[] = [];
  const groups = new Map<string, GroupedPageEvidence>();

  for (const row of rows) {
    const quote = row.source_text?.trim() ?? "";
    const key = quote.length >= 4 ? `quote:${normalizeQuoteText(quote)}` : `row:${row.card_evidence_id}`;

    let group = groups.get(key);
    if (!group) {
      group = {
        groupKey: key,
        sourceText: quote.length >= 4 ? normalizeQuoteText(quote) : null,
        items: [],
      };
      groups.set(key, group);
      order.push(key);
    }
    const factKey = factDedupeKey(row);
    if (!group.items.some((i) => factDedupeKey(i) === factKey)) {
      group.items.push(row);
    }
  }

  return order.map((k) => groups.get(k)!).filter((g) => g.items.length > 0);
}

/** Patterns + full quotes for PDF text-layer and plain-text highlighting. */
export type EvidenceHighlights = {
  patterns: string[];
  quoteTexts: string[];
};

const MAX_QUOTE_LEN = 600;

export function normalizeQuoteText(raw: string): string {
  return raw.replace(/\s+/g, " ").trim();
}

function isNumericToken(value: string): boolean {
  const compact = value.replace(/,/g, "").trim();
  return /^-?\d+(\.\d+)?%?$/.test(compact);
}

function addFullQuotePattern(quote: string, patterns: Set<string>) {
  patterns.add(quote);
}

/** Build regex patterns and quote corpus from mapped evidence on a page. */
export function buildEvidenceHighlights(evidence: EvidenceHighlightInput[]): EvidenceHighlights {
  const patterns = new Set<string>();
  const quoteTexts: string[] = [];

  const addQuote = (raw: string | null | undefined) => {
    if (!raw) return;
    const quote = normalizeQuoteText(raw);
    if (quote.length < 4) return;
    const clipped = quote.length > MAX_QUOTE_LEN ? quote.slice(0, MAX_QUOTE_LEN) : quote;
    quoteTexts.push(clipped);
    addFullQuotePattern(clipped, patterns);
  };

  for (const e of evidence) {
    addQuote(e.source_text);
    const formatted = formatEvidenceValue(e.evidence_value);
    const value = formatted ?? e.evidence_value?.trim() ?? null;
    if (!value || isNumericToken(value)) continue;
    addQuote(value);
  }

  // One entry per unique quote (panel dedupe may still pass overlapping rows).
  const uniqueQuotes = [...new Set(quoteTexts)];
  quoteTexts.length = 0;
  quoteTexts.push(...uniqueQuotes);
  patterns.clear();
  for (const q of uniqueQuotes) addFullQuotePattern(q, patterns);

  return {
    patterns: [...patterns].sort((a, b) => b.length - a.length),
    quoteTexts,
  };
}

/** @deprecated Prefer `buildEvidenceHighlights` — returns regex patterns only. */
export function evidenceHighlightPatterns(evidence: EvidenceHighlightInput[]): string[] {
  return buildEvidenceHighlights(evidence).patterns;
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escapeRegex(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function numericFlexibleRegex(digits: string): string | null {
  const core = digits.replace(/[^\d.]/g, "");
  if (!/^\d+(\.\d+)?$/.test(core)) return null;
  const [whole, frac] = core.split(".");
  const wholePart = whole
    .split("")
    .map((d, i) => (i === 0 ? d : `[,]?${d}`))
    .join("");
  return frac != null ? `${wholePart}(?:[.]?${frac.split("").join("[,]?")})?` : wholePart;
}

function flexibleTextRegex(text: string): string | null {
  const words = text.trim().split(/\s+/).filter((w) => w.length > 0);
  if (words.length < 2) return null;
  const gap = "[\\s\\-–—,;.:()]*";
  return words
    .map((w) => escapeRegex(w).replace(/\\-/g, "[\\s\\-–—]*"))
    .join(gap);
}

function normalizeMatchToken(raw: string): string {
  return raw.toLowerCase().replace(/[^a-z0-9%]/g, "");
}

function tokensMatch(spanToken: string, wordToken: string): boolean {
  if (!spanToken || !wordToken) return false;
  if (spanToken === wordToken) return true;
  if (spanToken.length >= 3 && wordToken.length >= 3) {
    return spanToken.includes(wordToken) || wordToken.includes(spanToken);
  }
  return false;
}

/** Walk PDF text-layer spans in order to mark a multi-word quote when regex on joined text fails. */
function matchQuoteToPdfSpans(
  spans: HTMLElement[],
  quote: string,
  hit: Set<HTMLElement>,
): boolean {
  const words = quote.split(/\s+/).map(normalizeMatchToken).filter((w) => w.length > 1);
  if (words.length < 2) return false;

  const spanTokens = spans.map((s) => normalizeMatchToken(s.textContent ?? ""));
  let matchedAny = false;
  let wi = 0;
  let startIdx = -1;

  for (let si = 0; si < spanTokens.length; si++) {
    const st = spanTokens[si];
    if (!st) {
      if (startIdx >= 0) {
        wi = 0;
        startIdx = -1;
      }
      continue;
    }

    if (tokensMatch(st, words[wi])) {
      if (startIdx < 0) startIdx = si;
      wi += 1;
      if (wi >= words.length) {
        for (let j = startIdx; j <= si; j++) hit.add(spans[j]);
        matchedAny = true;
        wi = 0;
        startIdx = -1;
      }
      continue;
    }

    if (startIdx >= 0) {
      si = startIdx;
      wi = 0;
      startIdx = -1;
    }
  }

  return matchedAny;
}

function buildHighlightRegex(patterns: string[]): RegExp | null {
  const parts: string[] = [];
  for (const pattern of patterns) {
    if (pattern.length < 2) continue;
    const noComma = pattern.replace(/,/g, "");
    const numeric = numericFlexibleRegex(noComma);
    if (numeric) {
      parts.push(numeric);
      continue;
    }
    const textual =
      pattern.length >= 8 && /[a-zA-Z]/.test(pattern) ? flexibleTextRegex(pattern) : null;
    parts.push(textual ?? escapeRegex(pattern));
  }
  if (parts.length === 0) return null;
  return new RegExp(`(${parts.join("|")})`, "gi");
}

type SpanRange = { el: HTMLElement; start: number; end: number };

function joinPdfTextSpans(spans: HTMLElement[]): { text: string; ranges: SpanRange[] } {
  let text = "";
  const ranges: SpanRange[] = [];
  for (const el of spans) {
    const piece = el.textContent ?? "";
    if (!piece) continue;
    if (
      text.length > 0 &&
      !/\s$/.test(text) &&
      !/^\s/.test(piece) &&
      /[\w%]$/.test(text) &&
      /^[\w%]/.test(piece)
    ) {
      text += " ";
    }
    const start = text.length;
    text += piece;
    ranges.push({ el, start, end: text.length });
  }
  return { text, ranges };
}

function quoteRegex(quote: string): RegExp | null {
  const flex = flexibleTextRegex(quote);
  if (flex) return new RegExp(flex, "gi");
  const single = quote.trim();
  if (single.length >= 6 && /[a-zA-Z]/.test(single)) {
    return new RegExp(escapeRegex(single), "gi");
  }
  return null;
}

function markSpanRange(ranges: SpanRange[], start: number, end: number, hit: Set<HTMLElement>) {
  for (const r of ranges) {
    if (r.end > start && r.start < end) hit.add(r.el);
  }
}

/**
 * Highlight only contiguous source-quote matches on a rendered PDF text layer.
 * Uses parsed `referenceText` (pipeline page_text) when the PDF text layer diverges.
 */
export function applyPdfPageHighlights(
  textLayer: HTMLElement,
  highlights: EvidenceHighlights,
  referenceText?: string | null,
): void {
  const spans = [...textLayer.querySelectorAll('[role="presentation"]')] as HTMLElement[];
  spans.forEach((el) => el.classList.remove("evidence-highlight"));

  if (spans.length === 0 || highlights.quoteTexts.length === 0) return;

  const { text: pdfText, ranges } = joinPdfTextSpans(spans);
  const hit = new Set<HTMLElement>();
  const refNorm = referenceText ? normalizeQuoteText(referenceText) : "";

  for (const quote of highlights.quoteTexts) {
    let matched = false;
    const re = quoteRegex(quote);
    if (re && pdfText) {
      for (const match of pdfText.matchAll(re)) {
        matched = true;
        const start = match.index ?? 0;
        markSpanRange(ranges, start, start + match[0].length, hit);
      }
    }
    if (!matched) {
      matched = matchQuoteToPdfSpans(spans, quote, hit);
    }
    if (!matched && refNorm) {
      const qNorm = normalizeQuoteText(quote);
      if (qNorm.length >= 8 && refNorm.includes(qNorm)) {
        matchQuoteToPdfSpans(spans, quote, hit);
      }
    }
  }

  hit.forEach((el) => el.classList.add("evidence-highlight"));
}

/** Wrap full source-quote matches in `<mark class="evidence-highlight">`. */
export function highlightMatchInText(text: string, patterns: string[]): string {
  const re = buildHighlightRegex(patterns);
  if (!re || !text) return escapeHtml(text);

  let result = "";
  let lastIndex = 0;
  for (const match of text.matchAll(re)) {
    const index = match.index ?? 0;
    result += escapeHtml(text.slice(lastIndex, index));
    result += `<mark class="evidence-highlight">${escapeHtml(match[0])}</mark>`;
    lastIndex = index + match[0].length;
  }
  result += escapeHtml(text.slice(lastIndex));
  return result;
}

/** Label for event `main_issue` — tone depends on overall verdict, not always a "problem". */
export function mainIssueLabel(overallSignal: SignalDirection | null | undefined): string {
  switch (overallSignal) {
    case "POSITIVE":
      return "Key risk";
    case "NEGATIVE":
      return "Main concern";
    case "MIXED":
      return "Key concern";
    default:
      return "Key focus";
  }
}

export function formatDate(d: string | null | undefined): string {
  if (!d) return "—";
  return new Date(d).toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

export function eventTypeLabel(type: string | null | undefined): string | null {
  if (!type) return null;
  return type.replace(/_/g, " ").toLowerCase();
}

/** Title-case document / event type for timeline row headings (e.g. "Investor presentation"). */
export function eventTypeTitle(type: string | null | undefined): string {
  const label = eventTypeLabel(type);
  if (!label) return "Event";
  return label.replace(/\b\w/g, (c) => c.toUpperCase());
}

const EVENT_TITLE_TYPE_SUFFIXES = [
  "Investor Presentation",
  "Concall Transcript",
  "Financial Results",
  "Quarterly Result",
  "Annual Report",
  "Press Release",
  "Exchange Filing",
  "Shareholding Pattern",
  "Credit Rating",
] as const;

/** Strip company / period prefix from legacy `event_title` when `event_type` is missing. */
export function eventTitleToTypeTitle(title: string | null | undefined): string | null {
  if (!title) return null;
  const trimmed = title.trim();
  for (const suffix of EVENT_TITLE_TYPE_SUFFIXES) {
    if (trimmed.toLowerCase().endsWith(suffix.toLowerCase())) {
      return suffix;
    }
  }
  const match = trimmed.match(/^.+?\s+Q\d\s+FY[\d-]+\s+(.+)$/i);
  return match?.[1]?.trim() ?? null;
}

/** Prefer enum-backed label; fall back to parsing `event_title`. */
export function resolveEventDisplayTitle(
  eventType: string | null | undefined,
  eventTitle: string | null | undefined,
): string {
  if (eventType) return eventTypeTitle(eventType);
  return eventTitleToTypeTitle(eventTitle) ?? "Event";
}

/** Extract `Q4 FY2025-26` from titles like `RELIANCE Q4 FY2025-26 Concall Transcript`. */
export function eventTitleToPeriodLabel(title: string | null | undefined): string | null {
  if (!title) return null;
  const match = title.trim().match(/\b(Q[1-4])\s+(FY\d{4}-\d{2})\b/i);
  if (!match) return null;
  return `${match[1].toUpperCase()} ${match[2].toUpperCase()}`;
}

export interface QuarterPeriodLike {
  display_label?: string;
  fy_label?: string;
  quarter?: number | null;
}

/** Reporting quarter label for timeline section headers (never the full event title). */
export function resolveQuarterPeriodLabel(
  period: QuarterPeriodLike | null | undefined,
  eventTitle?: string | null,
): string {
  if (period?.display_label) return period.display_label;
  if (period?.fy_label != null && period.quarter != null) {
    return `Q${period.quarter} ${period.fy_label}`;
  }
  const parsed = eventTitleToPeriodLabel(eventTitle);
  if (parsed) return parsed;
  return "Unknown period";
}

/** ISO date (YYYY-MM-DD) for grouping timeline rows on the same calendar day. */
export function timelineDateKey(d: string | null | undefined): string | null {
  if (!d) return null;
  const iso = d.slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(iso) ? iso : null;
}

export function relativeDate(d: string | null | undefined): string {
  if (!d) return "—";
  const date = new Date(d);
  const now = new Date();
  const ms = now.getTime() - date.getTime();
  const days = Math.floor(ms / (1000 * 60 * 60 * 24));
  if (days === 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 7) return `${days}d ago`;
  if (days < 30) return `${Math.floor(days / 7)}w ago`;
  if (days < 365) return `${Math.floor(days / 30)}mo ago`;
  return `${Math.floor(days / 365)}y ago`;
}

export function cardTypeLabel(type: string): string {
  // Mirror of `_CATEGORY_TO_CARD_TYPE` in
  // `backend/app/services/pipeline/cards.py`. Keep both in sync; falling
  // through to title-cased keys is fine for ad-hoc card types but the
  // canonical labels live here.
  const map: Record<string, string> = {
    result_verdict: "Result Verdict",
    revenue_growth: "Revenue Growth",
    growth_signal: "Growth",
    margin_movement: "Margin Movement",
    profit_quality: "Profit Quality",
    earnings_quality: "Earnings Quality",
    cash_quality: "Cash Quality",
    cashflow_signal: "Cash Flow",
    working_capital: "Working Capital",
    expense_pressure: "Expense Pressure",
    cost_pressure: "Cost Pressure",
    debt_signal: "Debt",
    solvency_signal: "Solvency",
    valuation_signal: "Valuation",
    market_reaction: "Market Reaction",
    governance_signal: "Governance",
    guidance_signal: "Guidance",
    order_book: "Order Book",
    segment_performance: "Segment Performance",
    red_flag: "Red Flag",
    watch_next: "What to Watch Next",
    management_signal: "Management",
    management_tone: "Management Tone",
    guidance_tracker: "Guidance Tracker",
    analyst_concern: "Analyst Concern",
    balance_sheet: "Balance Sheet",
  };
  return map[type] || type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
