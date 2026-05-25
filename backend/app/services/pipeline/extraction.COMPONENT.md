# services/pipeline/extraction

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Stage 1 of the pipeline. Reads parsed pages (text + rendered PNG), calls the
configured LLM provider OR replays a cached payload, runs deterministic
post-LLM validators, and persists structured numeric facts as `ExtractedValue`
rows tied to the originating `ExtractionJob` + `SourceDocument`.

## Source

- Path: `backend/app/services/pipeline/extraction.py`
- Layer: backend-service

## Contract

- `run_extraction(db, *, document, job, provider, model=None) -> ExtractionResult` —
  writes one `ExtractedValue` per validated item, marks
  `extraction_jobs.status = PROCESSING`, populates `model_name`,
  `prompt_version`, `parser_version`, `started_at`, `request_hash`,
  `raw_response`, `llm_temperature`, `llm_seed`, `provider_used`,
  `validator_report`, and rolls token / cost / overall-confidence + a
  `cache_hit` flag into the job's `meta`. ``model`` is the actual LLM model
  id used (after `llm.select_extraction_model` has run in
  `runner.run_pipeline_for_document`); when omitted, `settings.LLM_MODEL`
  is used. The chosen model is folded into `request_hash` so cache replays
  are scoped to the model that produced the cached payload.
- `_compute_request_hash(document, provider_name, model, seed) -> str` —
  sha256 over `(file_hash, PROMPT_VERSION, PARSER_VERSION, provider_name,
  model, seed)`. The cache key for the determinism contract.

## Determinism / cache contract

Given the same `(document.file_hash, PROMPT_VERSION, PARSER_VERSION,
provider.name, model, seed)`, re-running `run_extraction` produces the same
`ExtractedValue` rows. The mechanism:

1. Compute `request_hash`.
2. Look up the most recent `COMPLETED` or `NEEDS_REVIEW` `ExtractionJob` for
   the same `document_id` with a matching `request_hash` and a non-null
   `raw_response`.
3. **Cache hit:** parse the cached `raw_response` via
   `llm.parse_extraction_payload` and skip the provider call entirely. The
   replay path is byte-deterministic.
4. **Cache miss:** call the provider, persist `raw_response` + bookkeeping.

Bump `llm.PROMPT_VERSION` to force a global re-extraction across all
documents. Bump `parsing.PARSER_VERSION` if the page-image rendering or text
extraction changes in a way that should invalidate cached LLM outputs.

## Dependencies

- May import: `app.services.pipeline.llm`, `.parsing` (for `PARSER_VERSION`),
  `.storage` (for loading page images), `.validators`, `app.models.events`,
  `app.models.facts`.
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
- Validators (`validators.run_validators`) always run between the provider /
  replay step and the persistence step. The aggregated `ValidatorReport`
  lands on `extraction_jobs.validator_report` and is surfaced via
  `runner._review_description`.
- Confidence per item maps to `ConfidenceLevel` via the same thresholds the
  seed uses (HIGH ≥ 85, MEDIUM ≥ 65, LOW ≥ 40, else NEEDS_REVIEW). Keep these
  in sync with [seed_catalog.py](../../seed/seed_catalog.py).
- `SourceDocument.extraction_confidence` and `.values_extracted` are updated
  here so the admin Review Queue + drawer surface real numbers.

## Verification checklist

- [ ] Calling twice on the same document does not duplicate `ExtractedValue`s.
- [ ] `ExtractionJob.started_at`, `.model_name`, `.prompt_version`, and
      `.parser_version` are set before LLM call.
- [ ] Second call with an unchanged input replays from `raw_response` without
      hitting the provider (covered by `tests/test_extraction_cache.py`).
- [ ] `ExtractedValue.normalized_label` always matches the `normalized_code`
      from `financial_line_item_definitions`.
- [ ] `validator_report` reflects every breach surfaced by
      `validators.run_validators` (totals math, dropped source-text anchors,
      dropped unit aliases).
- [ ] Empty document (`no parsed pages`) is handled with notes, not a crash.
