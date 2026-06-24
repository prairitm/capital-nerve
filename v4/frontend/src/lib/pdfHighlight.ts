export type EvidenceHighlights = {
  patterns: string[];
  quoteTexts: string[];
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
    if (quote.length < 2) return;
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
      if (value && value.length >= 2) {
        addQuote(`${lineMatch[1]}. ${value}`);
        addQuote(value);
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
  const noComma = quote.replace(/,/g, "");
  const numeric = numericFlexibleRegex(noComma);
  if (numeric) return new RegExp(numeric, "gi");

  const flex = flexibleTextRegex(quote);
  if (flex) return new RegExp(flex, "gi");
  const single = quote.trim();
  if (single.length >= 2) {
    return new RegExp(escapeRegex(single), "gi");
  }
  return null;
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
      if (qNorm.length >= 4 && refNorm.includes(qNorm)) {
        matchQuoteToPdfSpans(spans, quote, hit);
      }
    }
  }

  hit.forEach((el) => el.classList.add("evidence-highlight"));

  const first = [...hit][0];
  if (first) {
    first.scrollIntoView({ block: "center", behavior: "smooth" });
  }
}
