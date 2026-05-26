# EventSignalDiagnosticsPanel

> Inherits: ./_BASE.md

## Purpose
Collapsible panel on the event detail page listing every signal rule the
pipeline evaluated — fired, not fired, and non-evaluable (concall-only).

## Source
- Path: `frontend/src/components/cards/EventSignalDiagnosticsPanel.tsx`
- Layer: frontend-component

## Contract
- Props: `{ diagnostics: EventSignalDiagnostics, className?: string }`
- Renders `null` when `rules_total === 0`

## Dependencies
- May import: `@/api/types`, `lucide-react`, `clsx`
- Must not: fetch data — parent passes `EventDetailV1.signal_diagnostics`

## UI / UX (frontend only)
- Collapsed by default; header shows fired / not fired / not evaluable counts
- Three sub-lists with colour-coded section titles

## Verification checklist
- [ ] Event with extraction job meta shows panel on `/company/:symbol/event/:id`
- [ ] Fired rows show headline when present
- [ ] `no_numeric_rule` rows appear under "Not evaluable"
