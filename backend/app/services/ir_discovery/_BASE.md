# services/ir_discovery

> Inherits: [../_BASE.md](../_BASE.md)

## Purpose

Owns the standalone bulk-ingest workflow driven by
[`app/scripts/bulk_ingest.py`](../../scripts/bulk_ingest.COMPONENT.md):

> CLI period range -> agent finds asset URLs per (Company × Period) -> we
> download each PDF -> we persist `CompanyEvent` + `SourceDocument` +
> `ExtractionJob` and run the same pipeline `POST /ingest/upload` runs.

This is a write-side service. It is allowed to insert / update rows in the
ingestion tables (`company_events`, `source_documents`, `extraction_jobs`,
`review_queue`, `financial_periods`) because it is essentially a
non-HTTP variant of the upload endpoint. It must NOT write to the rows
owned by the pipeline (`extracted_values`, `financial_statement_facts`,
`calculated_metrics`, `generated_signals`, `intelligence_cards`,
`card_evidence`, `document_pages`, `document_page_embeddings`) — those are
still produced by [`services/pipeline`](../pipeline/_BASE.md) when this
package calls `run_pipeline_for_document`.

## File layout

| File | Owns |
|------|------|
| [`__init__.py`](__init__.py) | Re-exports `expand_range`, `find_period_assets`, `ingest_one`. |
| [`schemas.py`](schemas.py) | `PeriodSpec`, `CompanyRef`, `AssetMatch`, `PeriodAssetSet`. |
| [`periods.py`](periods.py) | Quarter / date / last-N range expansion. Indian FY math. |
| [`agent.py`](agent.py) | OpenAI Agents SDK + WebSearchTool runner. |
| [`download.py`](download.py) | sha256 storage + human-browsable mirror. |
| [`ingest.py`](ingest.py) | Per-pair end-to-end: download + tables + pipeline. |

## Cross-cutting rules

- The OpenAI Agents SDK import (`agents.Agent`, `agents.WebSearchTool`)
  lives **only** in `agent.py`. Other modules consume `PeriodAssetSet`.
  Mirrors the LLM-provider isolation rule in
  [`services/pipeline/_BASE.md`](../pipeline/_BASE.md).
- `ingest_one` re-uses
  [`services/ingest_common`](../ingest_common.COMPONENT.md) for URL fetch,
  suffix detection, and period resolution. Do not re-implement those.
- Storage writes go through
  [`services/pipeline/storage.LocalStorage`](../pipeline/storage.py) — sha256
  content addressing keeps an S3 swap a one-file change.
- The package never raises `HTTPException`. Errors are surfaced through
  `IngestOutcome` so the CLI can render them and exit with a non-zero
  code without involving FastAPI.
- Idempotent: re-running a pair must be a no-op (we lean on
  `SourceDocument.file_hash` uniqueness + `LocalStorage` dedupe).

## Required reading before changes here

- [../ingest_common.COMPONENT.md](../ingest_common.COMPONENT.md) —
  shared helpers; do not re-implement.
- [../pipeline/runner.COMPONENT.md](../pipeline/runner.COMPONENT.md) —
  the pipeline `ingest_one` calls. Auto-publish gating lives there.
- [../../routers/ingest.COMPONENT.md](../../routers/ingest.COMPONENT.md) —
  the HTTP variant. The end-state in the DB MUST match what that
  endpoint produces.
