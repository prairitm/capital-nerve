# ReproducibilityExportButton

> Inherits: ./_BASE.md

## Purpose
Download the analyst-reproducibility bundle for an
`IntelligenceObject` as a JSON file. One click ⇒ one self-contained
file that lets an analyst (or another model) replay the verdict
offline.

## Source
- Path: `frontend/src/components/evidence/ReproducibilityExportButton.tsx`
- Layer: frontend-component

## Contract
- Props: `{ objectId: number, className?: string }`.
- Fetches `/v1/intelligence-objects/{objectId}/reproducibility` and
  streams the JSON via a blob anchor.

## Dependencies
- May import: `@/api/client`, `@/api/types`, `lucide-react`, `clsx`.
- Must not: render the bundle contents itself (use
  `ExtractionLineageGraph` for the inline view).

## Patterns (symmetry)
- Uses the same `btn-ghost`-style chrome as the other small detail-page
  actions (Back button, surface chips).
- Errors surface inline (single-line `text-negative` under the button)
  rather than via toast so the export interaction stays self-contained.

## UI / UX (frontend only)
- Tailwind tokens: `border-line/60`, `bg-surface-2/40`, `text-ink`.
- Disabled while the export is in flight; label switches to
  "Exporting…" so the user gets immediate feedback.

## Verification checklist
- [ ] File name is `intelligence-object-{id}-reproducibility.json`.
- [ ] Object URL is revoked after the click so blobs do not leak.
- [ ] Failure message appears under the button on API errors.
