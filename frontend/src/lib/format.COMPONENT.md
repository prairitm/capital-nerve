# lib/format

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Indian-locale formatters for numbers, currency in Crores, percentages, signed deltas, dates, and label strings used by feed surfaces.

## Source

- Path: `frontend/src/lib/format.ts`
- Layer: frontend-lib

## Contract

- Exports:
  - `formatNumber(n, fractionDigits = 0)` — `en-IN` locale.
  - `formatSigned(n, fractionDigits = 1, suffix = "")` — adds a `+` for positives.
  - `formatCr(value)` — switches to `L Cr` (`value / 100000`) when `|value| >= 100000`.
  - `formatPct(value, fractionDigits = 1)` — appends `%`.
  - `formatEvidenceValue(value)` — preserves pre-formatted evidence strings; strips float noise like `37146.000000` → `37,146`.
  - `buildEvidenceHighlights(evidence)` — full `source_text` quotes only; `highlightMatchInText` (plain text) and `applyPdfPageHighlights` (PDF text layer, contiguous match).
  - `dedupePageEvidenceRows(rows)` — one panel row per distinct label+value (prefers source quotes over calculated_metric).
  - `groupEvidenceBySourceText(rows)` — groups deduped rows that share the same source quote.
  - `formatDate(d)` — `dd MMM yyyy` in `en-IN`.
  - `relativeDate(d)` — `today / yesterday / Nd / Nw / Nmo / Ny ago`.
  - `eventTypeLabel(type)` — lower-cases and replaces `_` with space.
  - `eventTypeTitle(type)` — title-case label for timeline row headings (e.g. "Quarterly result").
  - `eventTitleToTypeTitle(title)` — strips company/period prefix from legacy `event_title` values.
  - `resolveEventDisplayTitle(eventType, eventTitle)` — prefers `eventTypeTitle`, then parsed title.
  - `eventTitleToPeriodLabel(title)` — extracts `Q# FY####-##` from legacy event titles.
  - `resolveQuarterPeriodLabel(period, eventTitle?)` — quarter header text only (never full `event_title`).
  - `timelineDateKey(d)` — ISO `YYYY-MM-DD` for grouping (validates format).
  - `mainIssueLabel(overallSignal)` — `"Key risk" | "Main concern" | "Key concern" | "Key focus"`.
  - `cardTypeLabel(type)` — explicit map, falls back to Title Case.

## Dependencies

- Imports `SignalDirection` type only.
- No React, router, or API calls.

## Patterns (symmetry)

- Null / undefined / `NaN` inputs return `"—"` (em dash). Components depend on this.
- All locale strings use `"en-IN"` to match the seeded Indian context.
- `mainIssueLabel` is the only place that decides the contextual label for an event/card's main issue — components call it instead of hard-coding the label.
- `cardTypeLabel` maintains an explicit dictionary; when you introduce a new card type, add it here.

## Verification checklist

- [ ] All numeric helpers return `"—"` for null / undefined / `NaN`
- [ ] Locale is `"en-IN"` everywhere
- [ ] `cardTypeLabel` covers every new card type
- [ ] `mainIssueLabel` callers never inline the label string
