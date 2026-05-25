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
- `ProviderPage(page_number, text, image_bytes)` — each page is text + an
  optional rendered PNG. The extraction stage loads PNGs from
  `DocumentPage.image_path` via the storage interface. Before the API call,
  `llm._fit_page_image_for_llm` downscales to ≤2000px and JPEG-compresses so
  Anthropic many-image and 32 MB body limits are respected (stored PNGs unchanged).
- `ExtractionResult` — `items: list[ExtractedLineItem]`, plus token / cost /
  confidence bookkeeping AND `temperature`, `seed`, `provider_used`,
  `raw_response`. The last four feed the determinism cache on
  `extraction_jobs`.
- `ExtractedLineItem.normalized_code` must match a row in
  `financial_line_item_definitions` (see [normalization](normalization.py)).
  The JSON Schema enforces this via an `enum` on `normalized_code`.
- `ExtractedLineItem.source_text` is always a single-value quote
  (`"{raw_label} {formatted_value}"`), never a full multi-column PDF table row.
- Values are scoped to the **Quarter Ended** column via
  [`quarter_column.enforce_quarter_ended_only`](quarter_column.py).
- `PROMPT_VERSION` — module constant; bumping this invalidates the extraction
  cache on `extraction_jobs.request_hash`.
- `_EXTRACTION_JSON_SCHEMA` — single source of truth for the structured-output
  contract. Anthropic consumes it as `tool.input_schema`; OpenAI consumes it
  as `response_format.json_schema.schema`.
- `parse_extraction_payload(raw_response) -> (items, overall, notes)` — the
  cached-replay entry point used by [`extraction.run_extraction`](extraction.py).
- `get_provider(*, model=None) -> LLMProvider` — picks the implementation
  based on `LLM_PROVIDER`. The `model` kwarg overrides `settings.LLM_MODEL`
  for a single call (used by the per-document-type fast lane in
  `runner.run_pipeline_for_document`). Falls back to mock when the configured
  provider's API key is missing (dev only — production refuses to boot).
- `select_extraction_model(document) -> str` — returns
  `settings.LLM_MODEL_FAST` for `CONCALL_TRANSCRIPT` /
  `INVESTOR_PRESENTATION` / `PRESS_RELEASE` / `ANNUAL_REPORT` documents when
  that env var is set, else `settings.LLM_MODEL`. `FINANCIAL_RESULT` is
  always on `LLM_MODEL` so the premium tier handles the dense
  Quarter-Ended P&L tables.
- `answer_from_context(question, chunks) -> RAGAnswerResult` — cited Q&A over
  retrieved document passages (read-side; used by `/search/ask`).

## Providers

| Name | Trigger | Notes |
|------|---------|-------|
| `MockProvider` | `LLM_PROVIDER=mock` (default) or missing key | Regex-based; deterministic; works offline. |
| `AnthropicProvider` | `LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY` set | Tool-use with strict `input_schema`; `temperature=0` when the model accepts it (omitted on Opus 4.7+); multimodal (per-page PNG + OCR text). System prompt + tool schema carry `cache_control: ephemeral` so repeat calls hit the prompt cache (~10× cheaper on the cached input blocks). |
| `OpenAIProvider` | `LLM_PROVIDER=openai` + `OPENAI_API_KEY` set | `response_format=json_schema strict`; `temperature=0`; `seed` from `LLM_SEED`; same multimodal contract. |

## Dependencies

- May import: `anthropic` (lazy, only inside `AnthropicProvider`), `openai`
  (lazy, only inside `OpenAIProvider`), `base64` / `json` / `re` from stdlib.
- Other stages must **not** import `anthropic` or `openai` directly — that
  contract keeps the mock provider viable for tests and CI.

## Patterns (symmetry)

- New providers go behind the same `LLMProvider` protocol and are wired into
  `get_provider()`. Never short-circuit by importing a provider class
  somewhere else in the pipeline.
- Anthropic/OpenAI providers do **not** silently fall back to the mock on
  failure. Exceptions propagate to `runner.run_pipeline_for_document`, which
  marks the job `FAILED` and surfaces it in the Review Queue. (Previously the
  dev-only `_fallback_to_mock` masked outages — removed in 0005.)
- All providers must populate `model_name`, `temperature`, `seed`, and
  `provider_used` so the cache + the admin Review Queue can explain why a
  given job's output looked the way it did.
- All structured-extraction prompts derive from `_EXTRACTION_SYSTEM_PROMPT` +
  `_EXTRACTION_JSON_SCHEMA`. Prompt drift between providers is impossible
  by construction.

## Verification checklist

- [ ] `get_provider()` returns `MockProvider` when `LLM_PROVIDER=anthropic`
      but no `ANTHROPIC_API_KEY` is configured (dev) and raises in prod.
- [ ] `get_provider()` returns `MockProvider` when `LLM_PROVIDER=openai`
      but no `OPENAI_API_KEY` is configured (dev) and raises in prod.
- [ ] `MockProvider.extract_financial_facts` returns at least one item for the
      seed-shaped quarterly P&L.
- [ ] `AnthropicProvider` calls `messages.create` with `temperature=0` when
      the model supports it (omitted for Opus 4.7+) and passes a single tool
      named `emit_financial_facts`.
- [ ] `AnthropicProvider` sends `system` as a list of content blocks with
      `cache_control: {"type":"ephemeral"}` and the same marker on the
      `emit_financial_facts` tool entry (prompt-cache breakpoints).
- [ ] `select_extraction_model(document)` returns `LLM_MODEL_FAST` only for
      transcript / presentation / press-release / annual-report documents
      and only when `LLM_MODEL_FAST` is set; everything else returns `LLM_MODEL`.
- [ ] `OpenAIProvider` calls `chat.completions.create` with `temperature=0`,
      `seed=settings.LLM_SEED`, and `response_format.type == "json_schema"`
      with `strict=True`.
- [ ] Page images sent to providers are ≤2000px JPEG (`_fit_page_image_for_llm`);
      at most `_MAX_PAGES_TO_SEND` (20) pages per request.
- [ ] `parse_extraction_payload` is the only function used by the cache
      replay path in `extraction.py`.
- [ ] No file outside this module imports `anthropic` or `openai`.
- [ ] Bumping `PROMPT_VERSION` forces a cache miss on every document
      (`test_extraction_cache.test_request_hash_incorporates_prompt_and_parser_versions`).
