/** Indian financial filings report crore amounts to two decimal places. */
export const CR_FRACTION_DIGITS = 2;

export function formatNumber(n: number | null | undefined, fractionDigits = 0): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return Number(n).toLocaleString("en-IN", {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  });
}

export function formatSigned(n: number | null | undefined, fractionDigits = 1, suffix = ""): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const sign = n > 0 ? "+" : "";
  return `${sign}${Number(n).toFixed(fractionDigits)}${suffix}`;
}

export function formatCrAmount(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (Math.abs(value) >= 100000) return `${(value / 100000).toFixed(2)} L`;
  return formatNumber(value, CR_FRACTION_DIGITS);
}

export function formatCr(value: number | null | undefined): string {
  const amount = formatCrAmount(value);
  if (amount === "—") return amount;
  return `${amount} Cr`;
}

export function formatPct(value: number | null | undefined, fractionDigits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value.toFixed(fractionDigits)}%`;
}

/** Full metric value string including unit. */
export function formatMetricValue(
  value: number | null | undefined,
  unit: string | null | undefined,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const u = (unit ?? "").trim().toLowerCase();
  if (u === "%") return formatPct(value, 1);
  if (u === "bps") return `${value >= 0 ? "+" : ""}${value.toFixed(0)} bps`;
  if (u === "x") return `${formatNumber(value, 2)}x`;
  if (u === "cr" || u === "crore" || u === "crores") return formatCr(value);
  if (u === "rs" || u === "rs.") return `Rs ${formatNumber(value, 2)}`;
  if (u === "days") return `${formatNumber(value, 0)} days`;
  if (u) return `${formatNumber(value, 2)} ${unit}`;
  return formatNumber(value, 2);
}

/** Numeric display when the unit is rendered separately (snapshot tables). */
export function formatSnapshotValue(value: number | null | undefined, unit: string | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const u = (unit ?? "").trim().toLowerCase();
  if (u === "%") return formatPct(value);
  if (u === "cr" || u === "crore" || u === "crores") return formatCrAmount(value);
  if (u === "rs" || u === "rs.") return formatNumber(value, 2);
  return formatNumber(value, 2);
}

export function formatDate(d: string | null | undefined): string {
  if (!d) return "—";
  const date = new Date(d);
  if (Number.isNaN(date.getTime())) return d;
  return date.toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

/** Indian FY quarter label from a period-end ISO date, e.g. "Q4 FY2024-25". */
export function formatPeriodLabel(periodEnd: string | null | undefined): string {
  if (!periodEnd) return "—";
  const iso = periodEnd.slice(0, 10);
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!m) return periodEnd;
  const year = Number(m[1]);
  const month = Number(m[2]);
  const fyStart = month >= 4 ? year : year - 1;
  const quarter = Math.floor(((month - 4 + 12) % 12) / 3) + 1;
  const fyEnd = String((fyStart + 1) % 100).padStart(2, "0");
  return `Q${quarter} FY${fyStart}-${fyEnd}`;
}

export function relativeDate(d: string | null | undefined): string {
  if (!d) return "—";
  const date = new Date(d);
  if (Number.isNaN(date.getTime())) return "—";
  const now = new Date();
  const ms = now.getTime() - date.getTime();
  const days = Math.floor(ms / (1000 * 60 * 60 * 24));
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 7) return `${days}d ago`;
  if (days < 30) return `${Math.floor(days / 7)}w ago`;
  if (days < 365) return `${Math.floor(days / 30)}mo ago`;
  return `${Math.floor(days / 365)}y ago`;
}

/** Title-case a consolidation basis token e.g. "CONSOLIDATED" -> "Consolidated". */
export function basisLabel(basis: string | null | undefined): string {
  if (!basis) return "";
  return basis
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

const INPUT_SCOPE_LABELS: Record<string, string> = {
  CURRENT: "Current quarter",
  PY: "Prior year",
  PQ: "Prior quarter",
};

export function inputScopeLabel(scope: string | null | undefined): string {
  if (!scope) return "";
  return INPUT_SCOPE_LABELS[scope.toUpperCase()] ?? scope;
}

/** Title-case an event type token e.g. "QUARTERLY_RESULT" -> "Quarterly Result". */
export function eventTypeLabel(type: string | null | undefined): string {
  if (!type) return "Event";
  return type
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
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

/** Strip company / period prefix from legacy titles when event_type is missing. */
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

/** Prefer enum-backed label; fall back to parsing the title. */
export function resolveEventDisplayTitle(
  eventType: string | null | undefined,
  eventTitle: string | null | undefined,
): string {
  if (eventType) return eventTypeLabel(eventType);
  return eventTitleToTypeTitle(eventTitle) ?? "Event";
}

/** Extract `Q4 FY2025-26` from titles like `RELIANCE Q4 FY2025-26 Concall Transcript`. */
export function eventTitleToPeriodLabel(title: string | null | undefined): string | null {
  if (!title) return null;
  const match = title.trim().match(/\b(Q[1-4])\s+(FY\d{4}-\d{2})\b/i);
  if (!match) return null;
  return `${match[1].toUpperCase()} ${match[2].toUpperCase()}`;
}

const PERIOD_ENDED_RE =
  /period ended\s+(?:(\d{1,2})\s+([A-Za-z]+)|([A-Za-z]+)\s+(\d{1,2}))\s*,?\s*(\d{4})/i;

/** Resolve quarter label from period_label, Q/FY tokens, or "period ended …" announcement text. */
export function resolvePeriodLabel(
  periodLabel: string | null | undefined,
  title: string | null | undefined,
): string | null {
  if (periodLabel) return periodLabel;
  const fromTitle = eventTitleToPeriodLabel(title);
  if (fromTitle) return fromTitle;
  const match = PERIOD_ENDED_RE.exec(title ?? "");
  if (!match) return null;
  const day = match[1] ?? match[4];
  const month = match[2] ?? match[3];
  const year = match[5];
  const monthNum = new Date(`${month} 15, ${year}`).getMonth() + 1;
  if (Number.isNaN(monthNum)) return null;
  const iso = `${year}-${String(monthNum).padStart(2, "0")}-${String(Number(day)).padStart(2, "0")}`;
  return formatPeriodLabel(iso);
}

/** Compact document heading: e.g. "Q2 FY2024-25 · Quarterly Result". */
export function documentDisplayTitle(
  doc: { title?: string | null; document_kind?: string | null },
  event?: {
    event_type?: string | null;
    period_label?: string | null;
    title?: string | null;
  } | null,
): string {
  const typeLabel = event
    ? resolveEventDisplayTitle(event.event_type, event.title ?? doc.title)
    : doc.document_kind
      ? eventTypeLabel(doc.document_kind)
      : eventTitleToTypeTitle(doc.title) ?? "Document";

  const period = resolvePeriodLabel(event?.period_label, event?.title ?? doc.title);

  if (period && typeLabel) return `${period} · ${typeLabel}`;
  return period ?? typeLabel ?? doc.title ?? "Document";
}
