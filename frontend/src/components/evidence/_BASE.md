# `frontend/src/components/evidence/` baseline

> Inherits: [../../_BASE.md](../../_BASE.md)

This folder owns the split-view evidence viewer used on the Document page.

## Responsibilities

- Render a `DocumentDetail` payload as a left-side paginated document viewer + right-side evidence panel.
- Map each `pages[].page_number` to a scrollable sheet; show how many evidence rows reference that page.
- Highlight evidence rows whose `page_number` matches the active page (updated by scroll or page controls).
- Render uploaded PDFs from `GET /documents/{id}/file` via `react-pdf`; seeded markdown filings use `MarkdownLite` when no stored file exists.

## Rules

- The viewer is a single composite component ([`EvidenceViewer.tsx`](EvidenceViewer.tsx)) — keep it self-contained rather than splitting the markdown renderer into a separate file.
- Page navigation reflects `?page=` in the URL via `useSearchParams` so deep links from `SourceDocumentLink` work.
- Do not introduce a heavyweight markdown library — the seeded content only uses headings, bold, lists, paragraphs, and pipe tables, which `MarkdownLite` already covers.
- Use only fields defined on `DocumentDetail` in [`@/api/types`](../../api/types.ts); if you need a new shape, add it to the backend `DocumentDetail` payload first.
- Source quotes are rendered with a left border (`border-l-2 border-line pl-3 italic`) — keep this treatment consistent across evidence surfaces.
- Signal and intelligence object pages use [`EvidenceInlineLink.tsx`](EvidenceInlineLink.tsx) for compact `p.N` / `source` links beside metrics — not a standalone evidence card.
- The full evidence list (with source quotes + page links + calculation text + confidence) is rendered by the shared [`EvidencePanel.tsx`](EvidencePanel.tsx). Use it on every surface that opens a single intelligence object (intelligence-object page, card drawer, event analyst summary) so the evidence treatment stays identical across the app.
- The structured Signal → Metric → Inputs explainability payload is rendered by [`CalculationChainPanel.tsx`](CalculationChainPanel.tsx). Mount it above the existing "How we computed this" collapsible — it answers _why this fired_, while `EvidencePanel` answers _where the numbers came from_.
