# services/pipeline/llm

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Hide the choice of LLM provider behind one interface. Anything that needs
structured financial extraction calls `get_provider().extract_financial_facts(...)`
and gets back an `ExtractionResult` regardless of provider.

## Source

- Path: `backend/app/services/pipeline/llm.py`
- Layer: backend-service

## Contract

- `LLMProvider` protocol — `extract_financial_facts(pages, document_title) -> ExtractionResult`.
- `ExtractionResult` — `items: list[ExtractedLineItem]`, plus token / cost /
  confidence bookkeeping.
- `ExtractedLineItem.normalized_code` must match a row in
  `financial_line_item_definitions` (see [normalization](normalization.py)) —
  the prompt enumerates the allowed values so the LLM cannot invent new codes.
  The current allow-list spans P&L, cash flow, balance sheet, working
  capital, shareholding, guidance, and order-book buckets — the same codes
  the seed defines and that the doc-type-specific extractors fall back to
  when the mock provider is in use.
- `get_provider() -> LLMProvider` — picks the implementation based on
  `LLM_PROVIDER` env var. Falls back to mock when the configured provider's API
  key is missing.

## Providers

| Name | Trigger | Notes |
|------|---------|-------|
| `MockProvider` | `LLM_PROVIDER=mock` (default) or missing key | Regex-based; deterministic; works offline. |
| `AnthropicProvider` | `LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY` set | Uses `anthropic.Anthropic`. Defensive JSON parser tolerates fenced output. |
| `OpenAIProvider` | `LLM_PROVIDER=openai` + `OPENAI_API_KEY` set | Uses `openai.OpenAI` chat completions. Same JSON prompt/parser as Anthropic. |

## Dependencies

- May import: `anthropic` (lazy, only inside `AnthropicProvider`), `openai`
  (lazy, only inside `OpenAIProvider`).
- Other stages must **not** import `anthropic` or `openai` directly — that
  contract keeps the mock provider viable for tests and CI.

## Patterns (symmetry)

- New providers go behind the same `LLMProvider` protocol and are wired into
  `get_provider()`. Never short-circuit by importing a provider class
  somewhere else in the pipeline.
- When an Anthropic or OpenAI call raises, the provider returns a
  `MockProvider` fallback so the pipeline still completes (degraded confidence).
- All providers must populate `model_name` so `extraction_jobs.model_name`
  is informative in the admin UI.

## Verification checklist

- [ ] `get_provider()` returns `MockProvider` when `LLM_PROVIDER=anthropic`
      but no `ANTHROPIC_API_KEY` is configured.
- [ ] `get_provider()` returns `MockProvider` when `LLM_PROVIDER=openai`
      but no `OPENAI_API_KEY` is configured.
- [ ] `MockProvider.extract_financial_facts` returns at least one item for the
      seed-shaped quarterly P&L (regression test against the fixture in
      [seed_catalog.py](../../seed/seed_catalog.py)).
- [ ] `_parse_llm_json_response` parses fenced (` ```json ... ``` `) responses.
- [ ] No file outside this module imports `anthropic` or `openai`.
