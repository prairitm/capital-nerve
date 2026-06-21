# services/pipeline/segment

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Stage 1f. Regex extractor for segment revenue / EBIT tables in quarterly
financial results. Persists ``SegmentFact`` rows and rolls the largest segment
into ``primary_segment_revenue`` / ``primary_segment_ebit`` ``ExtractedValue``
rows for segment metrics and signals.

## Source

- Path: `backend/app/services/pipeline/segment.py`
- Layer: backend-service

## Contract

- `is_segment_document(document) -> bool` — ``FINANCIAL_RESULT`` only.
- `run_segment_extraction(db, *, document, event) -> int` — rows written.

## Dependencies

- May import: `app.models.{events,facts}`, `app.db.enums`.
- Must not import: LLM modules.

## Verification checklist

- [ ] Returns 0 when document has no period or no segment table text.
- [ ] Largest segment maps to primary rollup extracted values.
- [ ] Re-ingest updates existing ``SegmentFact`` for same period/segment.
