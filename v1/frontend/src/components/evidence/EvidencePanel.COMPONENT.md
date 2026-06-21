# EvidencePanel

> Inherits: ./_BASE.md

## Purpose

Shared "Evidence" list rendered on any surface that opens a single
intelligence object (intelligence-object page, card drawer, event analyst
summary). Each row carries a source quote, the formatted value, optional
calculation text, a confidence score, and a page-anchored `SourceDocumentLink`.

## Source

- Path: `frontend/src/components/evidence/EvidencePanel.tsx`
- Layer: frontend-component

## Contract

Props:

```ts
{
  evidence: EvidenceItem[];        // from IntelligenceObject.evidence
  title?: string;                   // default "Evidence"
  subtitle?: string;
  className?: string;
  limit?: number | null;            // default 8; pass `null` for unlimited
}
```

Returns `null` when `evidence` is empty so callers can mount it unconditionally.

## Dependencies

- May import: `@/api/types`, `@/components/common/SourceDocumentLink`,
  `@/lib/format` (`formatEvidenceValue`), `clsx`.
- Must not: re-fetch evidence, parse markdown, or compute new fields. Always
  consume `evidence[]` from the API payload.

## Patterns (symmetry)

- Source quotes use the standard `border-l-2 border-line pl-3 italic`
  treatment from the evidence folder baseline.
- Numeric values go through `formatEvidenceValue` so pre-formatted strings
  ("Rs 12,345 Cr") stay intact while raw floats render cleanly.
- Confidence score colour tracks the same thresholds used by
  `ConfidenceBadge` (≥85% positive, ≥60% neutral, < 60% muted).
- `evidence_type` labels mirror the values written by
  `services/pipeline/cards.py` (`source_quote`, `extracted_value`,
  `calculated_metric`, `narrative`, `management_statement`).

## UI / UX

- Renders inside a `card p-5 md:p-6` shell so it lines up with neighbouring
  sections on `IntelligenceObjectPage`.
- `limit` caps the visible rows; the residual count is shown as a single
  muted line so the panel does not dominate the page.
- Each row is a self-contained block — no row-level click target. The
  document link is the only interactive element so the analyst's clicks go
  exactly where they intend.

## Verification checklist

- [ ] Returns `null` when `evidence` is empty.
- [ ] Renders the `evidence_label`, `evidence_value` (formatted),
      `evidence_type` label, and `source_text` quote when present.
- [ ] Each row with `document_id` renders a `SourceDocumentLink` jumping to
      `page_number` (or document root if missing).
- [ ] Honours the `limit` prop (default 8) and shows a "+N more" footer when
      truncated; `limit={null}` renders all rows.
- [ ] Confidence score chip colour tracks the `confidenceTone` thresholds.
