# services/pipeline

> Inherits: [../_BASE.md](../_BASE.md)

## Purpose

Owns the real-data ingestion pipeline. Given an uploaded source document, walks the canonical chain documented in [AGENTS.md](../../../../AGENTS.md):

```
storage bytes → parse → extract → normalize → metrics → signals → cards
```

This is the only package that may write to `extracted_values`,
`financial_statement_facts`, `calculated_metrics`, `generated_signals`,
`intelligence_cards`, `card_evidence`, `document_pages`, or `extraction_jobs`
during ingestion. Read-side `/v1` routers must continue to go through
[`intelligence_object_builder`](../intelligence_object_builder.py).

## File layout

| File | Owns |
|------|------|
| [`__init__.py`](__init__.py) | Re-exports `run_pipeline_for_document`. |
| [`storage.py`](storage.py) | Local-filesystem object store with S3-shaped interface. |
| [`parsing.py`](parsing.py) | PDF / text bytes → `DocumentPage` rows. |
| [`indexing.py`](indexing.py) | FTS + pgvector embeddings on `DocumentPage` rows. |
| [`llm.py`](llm.py) | Pluggable LLM client (`MockProvider`, `AnthropicProvider`, `OpenAIProvider`). |
| [`extraction.py`](extraction.py) | Stage 1 — pages → `ExtractedValue`. |
| [`normalization.py`](normalization.py) | Stage 2 — `ExtractedValue` → `FinancialStatementFact`. |
| [`metrics.py`](metrics.py) | Stage 3 — facts → `CalculatedMetric`. |
| [`signals.py`](signals.py) | Stage 4 — metrics → `GeneratedSignal` via `signal_definitions.rule_json`. |
| [`cards.py`](cards.py) | Stage 5 — signals → `IntelligenceCard` + `CardEvidence`. |
| [`segment.py`](segment.py) | Stage 1f — segment tables → `SegmentFact` + primary segment rollup. |
| [`announcement.py`](announcement.py) | Stage 1g — press-release order / M&A / dividend / capacity extraction. |
| [`presentation.py`](presentation.py) | Stage 1h — investor-deck TAM / mix / concentration / targets. |
| [`runner.py`](runner.py) | Orchestrator + `ExtractionJob` bookkeeping. |

## Cross-cutting rules

- **Do not skip a stage.** Even if a downstream consumer only needs cards,
  the pipeline must still write the upstream rows so evidence references back
  to a real `ExtractedValue` and a real `CalculatedMetric`.
- **Idempotency.** Each stage clears previously-written rows for the same
  document before writing new ones. Re-running the pipeline must be safe.
- **No schema changes.** Pipeline writes use existing tables; new columns are
  a separate change (with Alembic migration + COMPONENT update).
- **Publish gate.** The runner is the only place that flips `is_published` on
  the event / signals / cards. Confidence ≥ `AUTO_PUBLISH_CONFIDENCE` → publish
  immediately; below → stay unpublished and the Review Queue stays OPEN.
- **LLM provider isolation.** Nothing outside `llm.py` may import `anthropic` or
  `openai`. Other stages consume `ExtractionResult` only.

## Required reading before changes here

- [../../models/_BASE.md](../../models/_BASE.md) — table contracts.
- [../../seed/seed_catalog.py](../../seed/seed_catalog.py) — canonical
  metric / signal / line-item shapes the pipeline reads. Add new metrics
  or signals here, never inside a pipeline stage.
- [../intelligence_object_builder.py](../intelligence_object_builder.py) — the
  downstream consumer; do not break its assumptions about populated fields.
