export type EvidenceHighlights = {
  patterns: string[];
  quoteTexts: string[];
};

export type SourceBbox = {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
};

const MAX_QUOTE_LEN = 600;

export function normalizeQuoteText(raw: string): string {
  return raw.replace(/\s+/g, " ").trim();
}

function sourceLabel(raw: string): string {
  const label = raw.trim().split("|")[0].trim();
  return label.replace(/^\d+\.\s*/, "").trim();
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

/** Build highlight anchors from a pipeline source quote (table rows, line items, etc.). */
export function buildEvidenceHighlights(sourceTexts: string[]): EvidenceHighlights {
  const patterns = new Set<string>();
  const quoteTexts: string[] = [];

  const addQuote = (raw: string | null | undefined) => {
    if (!raw) return;
    const quote = normalizeQuoteText(raw);
    if (quote.length < 4) return;
    const clipped = quote.length > MAX_QUOTE_LEN ? quote.slice(0, MAX_QUOTE_LEN) : quote;
    if (!quoteTexts.includes(clipped)) quoteTexts.push(clipped);
    patterns.add(clipped);
  };

  for (const raw of sourceTexts) {
    if (!raw) continue;
    addQuote(raw);
    addQuote(sourceLabel(raw));

    const lineMatch = raw.trim().match(/^(\d+)\./);
    const valueMatch = raw.match(/-?[\d,]+\.?\d*/g);
    if (lineMatch && valueMatch) {
      const value = valueMatch[valueMatch.length - 1]?.replace(/,/g, "");
      const label = sourceLabel(raw);
      if (value && value.length >= 2 && label.length >= 4) {
        addQuote(`${label} ${value}`);
        addQuote(`${lineMatch[1]}. ${value}`);
      }
    }
  }

  return {
    patterns: [...patterns].sort((a, b) => b.length - a.length),
    quoteTexts,
  };
}

function escapeRegex(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
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
  const noComma = quote.replace(/,/g, "");
  const numeric = numericFlexibleRegex(noComma);
  if (numeric && !/[a-zA-Z]/.test(quote)) return new RegExp(numeric, "gi");
  return null;
}

function buildHighlightRegex(patterns: string[]): RegExp | null {
  const parts: string[] = [];
  for (const pattern of patterns) {
    if (pattern.length < 4) continue;
    const noComma = pattern.replace(/,/g, "");
    const numeric = numericFlexibleRegex(noComma);
    if (numeric && !/[a-zA-Z]/.test(pattern)) {
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

function markSpanRange(ranges: SpanRange[], start: number, end: number, hit: Set<HTMLElement>) {
  for (const r of ranges) {
    if (r.end > start && r.start < end) hit.add(r.el);
  }
}

export function applyPdfPageHighlights(
  textLayer: HTMLElement,
  highlights: EvidenceHighlights,
  referenceText?: string | null,
): boolean {
  const spans = [...textLayer.querySelectorAll('[role="presentation"]')] as HTMLElement[];
  spans.forEach((el) => el.classList.remove("evidence-highlight"));

  if (spans.length === 0 || highlights.quoteTexts.length === 0) return false;

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

  const first = [...hit][0];
  if (first) {
    first.scrollIntoView({ block: "center", behavior: "smooth" });
  }

  return hit.size > 0;
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

export function parseSourceBbox(raw: number[] | null | undefined): SourceBbox | null {
  if (!raw || raw.length < 4) return null;
  const [x0, y0, x1, y1] = raw;
  if (![x0, y0, x1, y1].every((n) => Number.isFinite(n))) return null;
  if (x1 <= x0 || y1 <= y0) return null;
  return { x0, y0, x1, y1 };
}
