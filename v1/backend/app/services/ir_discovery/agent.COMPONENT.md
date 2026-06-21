# services/ir_discovery/agent

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Async OpenAI Agents SDK runner that, given a `(CompanyTarget, PeriodSpec)`
pair, returns a structured `PeriodAssetSet` with direct PDF URLs for the
financial-results / transcript / presentation / annual-report assets.

Direct port of [`experiment/6/src/ir_agent/agent.py`](../../../../experiment/6/src/ir_agent/agent.py)
with three deltas:

1. The agent is parametrised by an explicit period label so it cannot
   silently substitute a different quarter.
2. The structured-output schema is `PeriodAssetSet` (no audio slot, with
   `annual_report` slot).
3. Annual-period requests use a different prompt asking only for the full
   annual report PDF.

## Source

- Path: `backend/app/services/ir_discovery/agent.py`
- Layer: backend-service

## Contract

- `find_period_assets(company, period, *, max_turns=20) -> PeriodAssetSet`
  (async).
- The `agents` package is imported lazily inside the function so unit
  tests that monkeypatch this entry point do not need the SDK installed.
- Reads model name from `settings.IR_AGENT_MODEL` (default `gpt-5.5`),
  falling back to the `IR_AGENT_MODEL` env var.
- The returned `PeriodAssetSet.company` is overwritten with the canonical
  `CompanyRef` derived from the input `CompanyTarget` so callers never
  trust the model echo.

## Dependencies

- May import: `agents.{Agent, Runner, WebSearchTool}` (lazy),
  `app.core.config.settings`, `.schemas.{CompanyTarget, PeriodSpec,
  PeriodAssetSet, CompanyRef}`.
- Must not import: SQLAlchemy session, `app.services.pipeline`,
  `app.services.ir_discovery.{download, ingest}`. The agent is a pure
  network call — DB writes happen in `ingest_one`.

## Patterns (symmetry)

- Two prompt constants: `_QUARTERLY_INSTRUCTIONS`,
  `_ANNUAL_INSTRUCTIONS`. Pick the right one in `_build_agent` based on
  `period.is_annual`.
- The user prompt is built from `CompanyTarget` fields only —
  `_user_prompt` never reads the SQLAlchemy session, so the function is
  safe to call from the CLI driver after the company snapshot has been
  taken.
- The CLI bounds concurrent calls to this function with an
  `asyncio.Semaphore(IR_AGENT_CONCURRENCY)`; do not add internal
  rate-limiting here.

## Verification checklist

- [ ] Quarterly periods produce a prompt that contains the EXACT
      `period.display_label` and forbids fallback to other quarters.
- [ ] Annual periods produce a prompt that asks only for the annual
      report PDF.
- [ ] `find_period_assets` always overwrites `company` on the returned
      object with the canonical `CompanyRef`.
- [ ] The `agents` package import is lazy (the file imports cleanly
      even when `openai-agents` is not installed).
