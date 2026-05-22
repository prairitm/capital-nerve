# SourceDocumentLink / SourceDocumentLinks

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Builds links to the document viewer and renders dedupable lists of evidence sources. Centralises the document-page URL shape and the source-list visual treatment.

## Source

- Path: `frontend/src/components/common/SourceDocumentLink.tsx`
- Layer: frontend-component (presentational + tiny helpers)

## Contract

- Exports:
  - `type SourceRef = { documentId: number; page?: number | null; label: string }`
  - `documentSourceHref(documentId, page?)` — returns `/documents/:id` or `/documents/:id?page=N`.
  - `uniqueSourceRefs(evidence, primary?)` — dedupes evidence rows by `(documentId, page)`; lets the caller pass an optional "primary" doc to surface first.
  - `SourceDocumentLink({ documentId, page, label, className?, onClick? })` — single `Link`.
  - `SourceDocumentLinks({ refs, className?, prefix? })` — comma-separated list (`Source: a · b · c`).

## Dependencies

- May import: `react-router-dom` (`Link`), `clsx`, `@/api/types`.
- Must not: call APIs; rebuild evidence URLs anywhere else.

## Patterns (symmetry)

- Every link to a document goes through `documentSourceHref()` so the `?page=` query stays consistent for deep links.
- Inside a clickable card, nested links call `e.stopPropagation()` via the default `onClick` handler in `SourceDocumentLinks`.
- Label fallbacks:
  - Primary doc with no label → `"Source document"`.
  - Evidence row with a label → `"<label> · p.<page>"` when page is set.
  - Evidence row without a label → `"Page N"` when page is set, else `"Source"`.

## UI / UX

- Link styling: `.ui-link font-medium`.
- List styling: `text-xs text-ink-soft leading-relaxed`, separator `<span className="text-line mx-1.5">·</span>`.

## Verification checklist

- [ ] All document links use `documentSourceHref`
- [ ] Multi-source lists dedupe via `uniqueSourceRefs`
- [ ] Nested links inside clickable cards stop propagation
- [ ] Label fallback order matches what `CardDetailDrawer` and `SignalDetailPage` expect
