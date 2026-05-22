# EvidenceInlineLink

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Small `ui-link` document references (`p.21`, `source`) placed inline beside metrics and values on signal and intelligence object pages — replaces standalone evidence cards.

## Source

- Path: `frontend/src/components/evidence/EvidenceInlineLink.tsx`
- Layer: frontend-component

## Contract

- `evidenceMatchingLabel(evidence, ...labels)` — fuzzy match on normalized `evidence_label` / `evidence_value`.
- `EvidenceInlineLinks({ items })` — renders zero or more `SourceDocumentLink` chips; requires `document_id`.

## Dependencies

- May import: `@/api/types`, `@/components/common/SourceDocumentLink`.
- Must not: fetch data or render full evidence bodies (values, quotes, calculations).

## Verification checklist

- [ ] Links use `documentSourceHref` via `SourceDocumentLink`
- [ ] Page deep links when `page_number` is set
- [ ] Returns null when no linked evidence
