# services/ir_discovery/schemas

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Wire formats for the bulk-ingest workflow: the dataclass `PeriodSpec` (one
quarter or annual reporting window), the dataclass `CompanyTarget`
(threadsafe projection of a `Company` row that survives the agent's async
boundary), and the Pydantic `PeriodAssetSet` that the OpenAI Agents SDK
forces the model to return.

## Source

- Path: `backend/app/services/ir_discovery/schemas.py`
- Layer: backend-service-shape

## Contract

- `PeriodSpec(fy_year, period_type, quarter, period_start, period_end,
  fy_label, display_label)` — frozen dataclass; `is_quarterly` and
  `is_annual` properties for cheap branching.
- `CompanyTarget(company_id, company_name, nse_symbol, bse_code,
  investor_relations_url)` — frozen dataclass; the agent and the
  downloader receive this instead of the raw ORM `Company` so async code
  never lazy-loads against a closed session.
- `PeriodAssetSet` — Pydantic model with: `company`, `period: str`,
  `financial_report_pdf?`, `transcript?`, `presentation?`,
  `annual_report?`, `notes?`. All asset slots are `AssetMatch | None`.
  Audio is intentionally absent; the pipeline has no audio extractor.
- `DOC_TYPE_BY_ASSET_KEY: dict[str, (EventType, DocumentType)]` — the
  one source of truth mapping each asset slot to its
  `EventType + DocumentType` enum pair. `ingest_one` iterates this dict.

## Dependencies

- May import: `pydantic`, `app.db.enums.{DocumentType, EventType,
  PeriodType}`.
- Must not import: `agents` (the OpenAI Agents SDK), SQLAlchemy session
  helpers, or anything from `app.services.pipeline`.

## Patterns (symmetry)

- Adding a new asset slot is a 3-step change: add it to `PeriodAssetSet`,
  add the matching `(EventType, DocumentType)` row to
  `DOC_TYPE_BY_ASSET_KEY`, then teach the agent prompt in `agent.py` to
  request it. `ingest_one` automatically picks up the new key with no
  edits.
- `PeriodAssetSet.period` is a free-form string echoed back from the
  agent. `ingest_one` does not parse it; the canonical period info lives
  on the `PeriodSpec` we passed in.

## Verification checklist

- [ ] All asset fields on `PeriodAssetSet` default to `None`.
- [ ] `DOC_TYPE_BY_ASSET_KEY` has an entry for every non-`company` /
      `period` / `notes` field on `PeriodAssetSet`.
- [ ] `CompanyTarget` is `frozen=True` (safe to share across coroutines).
- [ ] No SQLAlchemy ORM imports in this file.
