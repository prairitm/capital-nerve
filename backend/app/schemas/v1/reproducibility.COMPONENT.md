# schemas/v1/reproducibility

> Inherits: ./_BASE.md

## Purpose
Pydantic shapes for the analyst-reproducibility export and the
`ExtractedValue → Fact → Metric → Signal → Card` lineage graph
returned by `GET /v1/intelligence-objects/{id}/reproducibility`.

## Source
- Path: `backend/app/schemas/v1/reproducibility.py`
- Layer: backend-schema

## Contract
- `ReproducibilityBundle` — top-level payload.
- `ReproducibilityCard`, `ReproducibilitySignal`,
  `ReproducibilityMetric`, `ReproducibilityInput`,
  `ReproducibilityAuditTrail` — domain pieces.
- `LineageGraph` with `LineageNode` (`kind` ∈
  `extracted_value | financial_fact | calculated_metric | generated_signal | intelligence_card`)
  and `LineageEdge`.

## Dependencies
- May import: pydantic only.
- Must not: import ORM models or service modules.

## Patterns (symmetry)
- Node `id` is a type-prefixed primary key (`extracted_value:42`)
  matching the convention in
  `services/reproducibility.py` and consumed by the frontend
  `ExtractionLineageGraph` component.
- All `*_score` confidence fields are `0..100` floats — same scale as
  every other confidence on the v1 surface.

## Verification checklist
- [ ] Any change to the bundle is mirrored in
      [frontend/src/api/types.ts](../../../../frontend/src/api/types.ts)
      (`ReproducibilityBundle` and friends).
- [ ] New node kinds added here must be added to the
      `LANE_ORDER` array in
      [frontend/src/components/evidence/ExtractionLineageGraph.tsx](../../../../frontend/src/components/evidence/ExtractionLineageGraph.tsx).
