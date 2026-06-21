# MetricConfidenceBadge

> Inherits: ./_BASE.md

## Purpose
Surface the extraction-confidence band (High / Medium / Low) for the
metric powering a feed card, alongside `MetricKindBadge` and
`MetricValidationBadge` in the trigger-metric strip.

## Source
- Path: `frontend/src/components/common/MetricConfidenceBadge.tsx`
- Layer: frontend-component

## Contract
- Props: `{ band: MetricConfidenceBand, score?: number | null, className?: string }`.
- `MetricConfidenceBand` (from `@/api/types`) is `"high" | "medium" | "low"`.

## Dependencies
- May import: `@/api/types`, `clsx`.
- Must not: re-derive the band from a raw score (the backend owns the
  threshold logic in
  [services/intelligence_object_builder.py](../../../../backend/app/services/intelligence_object_builder.py)
  via `_confidence_summary`).

## Patterns (symmetry)
- Visual treatment matches `MetricValidationBadge`: same border /
  background tokens, same uppercase `tracking-wider` typography.
- Tooltip includes the raw `confidence_score` when present, the band
  label otherwise.

## UI / UX (frontend only)
- Tailwind tokens: `text-positive`, `text-mixed`, `text-negative` for
  high / medium / low respectively.
- Always rendered inline inside `TriggerMetricStrip` — never standalone.

## Verification checklist
- [ ] Backend thresholds (≥ 80 high, ≥ 60 medium, else low) match the
      mapping in `_confidence_summary`.
- [ ] Tooltip shows the raw score when supplied.
- [ ] Component renders nothing when `band` is missing — callers must
      guard with `{confidence_band && <... />}` (see
      [TriggerMetricStrip.tsx](../cards/TriggerMetricStrip.tsx)).
