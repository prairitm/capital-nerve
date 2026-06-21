# EvidenceViewer

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Split-view document viewer rendered inside the Document page. Left pane stacks paginated document sheets with a page index; right pane shows extracted evidence for the active page, document metadata, and insights surfaced from this filing.

## Source

- Path: `frontend/src/components/evidence/EvidenceViewer.tsx`
- Layer: frontend-component (smart — reads URL state)

## Contract

- Export: `export function EvidenceViewer({ doc }: { doc: DocumentDetail })`

## Dependencies

- May import: `react`, `react-router-dom` (`useSearchParams`), `react-pdf`, `lucide-react`, `clsx`, `@/api/client` (`apiBlob`), `@/api/types`, `@/lib/format`, `@/components/common/Spinner` (`PageLoader`).
- Must not: import a heavyweight markdown library. The lightweight `MarkdownLite` renderer here is the canonical demo renderer for seeded text filings.

## Patterns (symmetry)

- Active page is initialized from `?page=` when present; otherwise the lowest `page_number` with evidence. On first open, the viewer scrolls to that page once PDF/text content is ready.
- Scroll position updates the URL via `IntersectionObserver` after the initial scroll; `?page=` deep links from `SourceDocumentLink` still take precedence.
- `pageEvidence` is filtered by `page_number === activePage` so evidence highlighting follows page changes.
- Left pane renders every `DocumentPage` as a bordered sheet with a sticky `Page N` header and an evidence-count chip when rows map to that page number.
- Desktop page index (narrow rail) and mobile page strip both call `selectPage`, which scrolls the sheet and updates `?page=`.
- When `has_source_file` and `source_content_type` includes `pdf`, fetch `/documents/{id}/file` via `apiBlob`, render pages with `react-pdf` (`Document` + `Page`). Seeded filings without storage fall back to `MarkdownLite` / `whitespace-pre-wrap`.
- PDF pages call `applyPdfPageHighlights` after the text layer renders (`onRenderTextLayerSuccess`) so only **contiguous** source-quote matches are marked — not isolated short phrases elsewhere on the page.
- PDF documents expose a **Full screen** control (`Maximize2`) that opens `PdfFullscreenOverlay` — fixed overlay with page rail, prev/next, evidence highlights, Escape/backdrop to close.
- Page-switcher controls use `btn-brand-active` for the active page and `bg-surface-2 text-ink-mute hover:text-ink` for inactive ones.
- Metadata block uses a 2-column grid with a small `Meta` subcomponent — reuse this helper rather than inlining label/value pairs.
- Source quotes render with `border-l-2 border-line pl-3 italic` to match the rest of the evidence treatment.
- Active-page panel: `dedupePageEvidenceRows` then `groupEvidenceBySourceText` — each fact once per page; shared quotes grouped under one card. PDF highlighting uses the **same deduped** evidence plus parsed `page_text` as reference when the PDF text layer diverges from extraction.

## UI / UX

- Outer grid: `grid grid-cols-1 lg:grid-cols-2 gap-4`.
- Document pane scrolls inside `max-h-[70vh]` with stacked page sheets on `bg-bg-deep/40`.
- Markdown features supported: `#`/`##` headings, bold (`**...**`), pipe tables, bullet lists, paragraphs. HTML escaping happens in `renderInline`.
- Plain extracted text preserves line breaks via `whitespace-pre-wrap`.

## Verification checklist

- [ ] Page index + scroll sync update `activePage`, `?page=`, and the highlighted evidence
- [ ] Each page sheet shows its page number and mapped evidence count
- [ ] PDF/plain text renders with preserved whitespace when content is not markdown
- [ ] Markdown rendering stays inside `MarkdownLite` — no external library
- [ ] Source quote treatment (italic + left border) matches the rest of the app
- [ ] `Meta` helper used for metadata key/value pairs
