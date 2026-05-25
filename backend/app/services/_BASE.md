# `backend/app/services/` baseline

> Inherits: [../_BASE.md](../_BASE.md)

Two kinds of services live here:

1. **Read-only enrichment** for routers (the original purpose).
2. **The ingestion pipeline** under [`pipeline/`](pipeline/_BASE.md) — write-side.
   This is the *only* package in `services/` that may issue INSERT / UPDATE /
   DELETE during ingestion. Read services stay read-only.

## Read-only modules

- [`card_context.py`](card_context.py) — calculated metric comparisons, trend sparklines, and concall heatmaps used by `GET /cards/{card_id}`.
- [`signal_context.py`](signal_context.py) — related cards, related signals, trigger metric, and evidence for `GET /signals/{signal_id}`.
- [`intelligence_object_builder.py`](intelligence_object_builder.py) — single derivation point for the v1 `IntelligenceObject` shape (`build_intelligence_object`, `build_intelligence_object_brief`). All v1 IO endpoints go through this module.
- [`portfolio_monitor.py`](portfolio_monitor.py) — `POST /v1/portfolio/monitor` aggregator.
- [`peer_narrative.py`](peer_narrative.py) — `GET /v1/companies/{symbol}/peer-narrative` theme clustering.
- [`credit_risk.py`](credit_risk.py) — credit-only slice of generated signals + dimension bucketing.
- [`retail_summary.py`](retail_summary.py) — retail-facing summary aggregator.
- [`result_brief_builder.py`](result_brief_builder.py) — sell-side analyst quarterly brief.
- [`unified_ask.py`](unified_ask.py) — natural-language ask; routes to SQL or RAG (`POST /search/ask`).
- [`data_ask.py`](data_ask.py) — read-only SQL over financial facts (used by `unified_ask`).
- [`document_rag.py`](document_rag.py) — cited Q&A over ingested filing pages (used by `unified_ask`).

## Pipeline (write-side, ingestion)

- [`pipeline/`](pipeline/_BASE.md) — full ingestion pipeline. Has its own
  baseline doc; new pipeline files MUST follow that baseline, not this one.

## Rules

- Read-side services accept a `Session` and read-only inputs (ids, ORM objects
  already fetched by the router). They never accept the `Request` object and
  never raise `HTTPException`.
- Read-side services return Pydantic objects (`CardMetricComparison`,
  `FinancialTrend`, ...) from [`../schemas/common.py`](../schemas/common.py),
  not raw dicts.
- Read-side services do not write. If a feature needs to mutate, put the
  mutation in the router and keep the service for read-side enrichment. The
  one exception is the pipeline package (see its [`_BASE.md`](pipeline/_BASE.md)).
- Add a new read-only service file only when you have more than one query
  helper for a single feature; one-off helpers can stay in the router.
- Constants tied to product rules (e.g. `CONCALL_CARD_TYPES`,
  `HIGHLIGHT_METRIC_CODES` in `card_context.py`) belong at module scope at the
  top of the file.
