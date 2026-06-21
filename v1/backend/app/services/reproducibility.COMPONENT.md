# reproducibility

> Inherits: ./_BASE.md

## Purpose
Assemble the analyst-reproducibility bundle for one `IntelligenceCard`:
signal rule, metric formula, resolved inputs, source quotes, pipeline
audit trail, and the `ExtractedValue → Fact → Metric → Signal → Card`
lineage graph in a single JSON payload.

## Source
- Path: `backend/app/services/reproducibility.py`
- Layer: backend-service

## Contract
- `build_reproducibility_bundle(db, card) -> ReproducibilityBundle`
- Returned `ReproducibilityBundle` schema lives in
  [schemas/v1/reproducibility.py](../schemas/v1/reproducibility.py).

## Dependencies
- May import: SQLAlchemy `Session`, ORM models in `app.models.events`,
  `app.models.facts`, and `app.models.intelligence`, plus the schema
  module `app.schemas.v1.reproducibility`.
- Must not: import any router module, mutate state, or call
  `intelligence_object_builder` (this service is read-only and
  side-effect free).

## Patterns (symmetry)
- Re-uses the input-resolution helpers from
  `intelligence_object_builder` conceptually (declared inputs zipped
  with `CalculatedMetric.input_values`) but does not import them so the
  reproducibility surface can evolve independently.
- Lineage nodes use a stable type-prefixed `id` (e.g.
  `extracted_value:42`) so the frontend graph can address them
  deterministically.

## Verification checklist
- [ ] Every input that resolved to an `ExtractedValue` shows up as an
      `extracted_value` node in the lineage graph.
- [ ] Each linked `FinancialStatementFact` (matched via
      `source_extracted_value_id`) shows up as a `financial_fact` node.
- [ ] Cards written post Phase 3 hydrate `audit_trail` from
      `display_context['audit_trail']` without re-joining
      `extraction_jobs`. Older cards fall back to the latest
      `ExtractionJob` row for the document.
- [ ] Result-verdict cards (no signal) still produce a bundle with
      `signal=None`, `metric=None`, and a card-level lineage edge.
