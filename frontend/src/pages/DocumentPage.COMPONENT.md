# DocumentPage

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Thin shell around `EvidenceViewer` at `/documents/:documentId`. Renders the document title, company link, and the split-view evidence viewer.

## Source

- Path: `frontend/src/pages/DocumentPage.tsx`
- Route: `/documents/:documentId`
- Layer: frontend-page

## Contract

- Data: `GET /documents/:documentId` (`DocumentDetail`).
- Action: `POST /documents/:documentId/reextract` — re-runs pipeline on the stored file for this document only (`202` + `job_id`).

## Dependencies

- May import: `react-router-dom`, `@tanstack/react-query`, `lucide-react` (`ArrowLeft`, `RefreshCw`), `@/api/client`, `@/api/types`, `@/components/common/Spinner` (`PageLoader`), `@/components/evidence/EvidenceViewer`.
- Must not: re-render the markdown itself — delegate to `EvidenceViewer`.

## Patterns (symmetry)

- Query key: `["document", documentId]`. Poll every 2.5s while `extraction_status` is `PENDING` or `PROCESSING`.
- "Re-extract file" calls `POST /documents/:id/reextract`; disabled while a job is active or the mutation is in flight.
- Renders "Document not found." when `data` is missing post-load.
- "Back" button uses `navigate(-1)` so deep links from a card preserve the previous scroll context.

## Verification checklist

- [ ] Page is the thinnest possible wrapper — viewer logic stays in `EvidenceViewer`
- [ ] Query key includes the document id
- [ ] `PageLoader` used while loading
- [ ] Back button uses `navigate(-1)`
- [ ] Re-extract button only when `has_source_file`; polls until extraction finishes
