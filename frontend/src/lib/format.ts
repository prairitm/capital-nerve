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

/** Search strings for highlighting evidence values in PDF text layers and text fallbacks. */
export function evidenceHighlightPatterns(evidence: EvidenceHighlightInput[]): string[] {
  const patterns = new Set<string>();

  const add = (raw: string | null | undefined) => {
    if (!raw) return;
    const trimmed = raw.trim();
    if (trimmed.length < 2) return;
    patterns.add(trimmed);
    const noComma = trimmed.replace(/,/g, "");
    if (noComma.length >= 2 && noComma !== trimmed) patterns.add(noComma);
  };

  for (const e of evidence) {
    add(e.evidence_value);
    add(formatEvidenceValue(e.evidence_value));
    if (e.source_text) {
      for (const m of e.source_text.match(/\d[\d,]*(?:\.\d+)?/g) ?? []) {
        add(m);
      }
      const quote = e.source_text.trim();
      if (quote.length >= 4 && quote.length <= 120) add(quote);
    }
  }

  return [...patterns].sort((a, b) => b.length - a.length);
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

function buildHighlightRegex(patterns: string[]): RegExp | null {
  const parts: string[] = [];
  for (const pattern of patterns) {
    if (pattern.length < 2) continue;
    const noComma = pattern.replace(/,/g, "");
    const flex = numericFlexibleRegex(noComma);
    parts.push(flex ?? escapeRegex(pattern));
  }
  if (parts.length === 0) return null;
  return new RegExp(`(${parts.join("|")})`, "gi");
}

/** Wrap pattern matches in `<mark class="evidence-highlight">` for PDF text layers. */
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
