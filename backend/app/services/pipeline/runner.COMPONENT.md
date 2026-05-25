# services/pipeline/runner

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

The orchestrator. The only entrypoint the worker and the future "re-run"
admin action call. Walks every stage in order, manages the
`extraction_jobs` row, updates the matching `review_queue` row, and decides
whether to auto-publish the resulting cards.

## Source

- Path: `backend/app/services/pipeline/runner.py`
- Layer: backend-service

## Contract

- `run_pipeline_for_document(db, *, job_id) -> PipelineSummary`.
- `PipelineSummary` exposes counts per stage, the final `ExtractionStatus`,
  the publish flag, and any error message.
- On failure: rolls back, sets `ExtractionJob.status = FAILED`, writes the
  error to `ExtractionJob.error_message` AND to the matching
  `ReviewQueue.issue_description` so the admin UI surfaces it.

## Dependencies

- May import: every other module in `services/pipeline/`, `app.models.*`,
  `app.core.config`.
- Must not import: routers (avoids circular imports — pipeline runs server-side).

## Patterns (symmetry)

- Stages run in this exact order: parsing → extraction → **doc-type-specific
  extractors** → normalization → metrics → signals → cards. Skipping or
  reordering breaks evidence traceability — see
  [AGENTS.md](../../../../AGENTS.md) for the rule.
- The extraction-model decision lives here, not in `extraction.run_extraction`:
  the runner calls `llm.select_extraction_model(document)` to choose between
  `LLM_MODEL` and `LLM_MODEL_FAST`, then passes that string both into
  `get_provider(model=...)` and into `run_extraction(model=...)` so the
  request-hash cache keys on the actually-used model.
- The doc-type extractors run conditionally between LLM extraction and
  normalization:
  - [`shareholding`](shareholding.py) when `event.event_type ==
    SHAREHOLDING_PATTERN`.
  - [`guidance`](guidance.py) for IR / concall / annual report / press
    release documents.
  - [`concall`](concall.py) when `document.document_type ==
    CONCALL_TRANSCRIPT`.
  - [`orderbook`](orderbook.py) for IR / concall / annual report / press
    release / financial result documents.
  Each writes additional `ExtractedValue` rows so the rest of the pipeline
  is unchanged. Counts land in `ExtractionJob.meta.stages.supplemental_*`.
- The publish gate is the **only** place `event.is_published` / signal /
  card `is_published` is flipped automatically. The same flip is mirrored in
  [`routers/review.py`](../../routers/review.py) for the manual-approval
  path; if you change one, change the other.
- Review queue updates use the most recent open review for the document so
  re-runs do not pile up multiple review rows.

## Verification checklist

- [ ] Auto-publish requires `period_id`, facts written, and confidence ≥
      `AUTO_PUBLISH_CONFIDENCE`
      on event/signals/cards and `ReviewQueue.status="RESOLVED"`.
- [ ] Confidence below threshold leaves everything unpublished and the
      review row OPEN.
- [ ] Any exception in a stage rolls back the transaction and writes
      `error_message` to both `ExtractionJob` and the active review row.
- [ ] `PipelineSummary` counts match the actual row counts written in the DB.
- [ ] `_populate_event_summary` uses [`event_summary.build_event_summary_text`](../event_summary.py) — not the legacy "Pipeline-generated brief" placeholder.
