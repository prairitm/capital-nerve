# services/pipeline/extraction

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Stage 1 of the pipeline. Reads parsed pages, calls the configured LLM
provider, and persists structured numeric facts as `ExtractedValue` rows tied
to the originating `ExtractionJob` + `SourceDocument`.

## Source

- Path: `backend/app/services/pipeline/extraction.py`
- Layer: backend-service

## Contract

- `run_extraction(db, *, document, job, provider) -> ExtractionResult` —
  writes one `ExtractedValue` per item the provider returned, marks
  `extraction_jobs.status = PROCESSING`, populates `model_name`, `started_at`,
  and rolls token / cost / overall-confidence into the job's `meta`.

## Dependencies

- May import: `app.services.pipeline.llm`, `app.models.events`, `app.models.facts`.
- Must not import: other pipeline stages, routers.

## Patterns (symmetry)

- Re-runs delete existing `ExtractedValue` rows for the document before
  inserting fresh ones — pipeline is idempotent. First null
  `source_extracted_value_id` / `extracted_value_id` FKs on facts, segment
  facts, card evidence, and review rows that still point at those IDs.
- The runner immediately follows this stage with the doc-type-specific
  extractors — [`shareholding`](shareholding.py), [`guidance`](guidance.py),
  [`concall`](concall.py), [`orderbook`](orderbook.py) — which append more
  `ExtractedValue` rows for the same document. Those modules rely on this
  stage having already cleared prior rows, so they don't repeat the wipe.
- Confidence per item maps to `ConfidenceLevel` via the same thresholds the
  seed uses (HIGH ≥ 85, MEDIUM ≥ 65, LOW ≥ 40, else NEEDS_REVIEW). Keep these
  in sync with [seed_catalog.py](../../seed/seed_catalog.py).
- `SourceDocument.extraction_confidence` and `.values_extracted` are updated
  here so the admin Review Queue + drawer surface real numbers.

## Verification checklist

- [ ] Calling twice on the same document does not duplicate `ExtractedValue`s.
- [ ] `ExtractionJob.started_at` and `.model_name` are set before LLM call.
- [ ] `ExtractedValue.normalized_label` always matches the `normalized_code`
      from `financial_line_item_definitions`.
- [ ] Empty document (`no parsed pages`) is handled with notes, not a crash.
