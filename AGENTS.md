# Agent Standards Index

CapitalNerve is an Indian-markets intelligence layer built around the workflow:

> Company → Event → Signal → Card → Evidence → Watch Item

Every meaningful source file has a colocated standards markdown so changes stay symmetric with the rest of the code. Before editing any file, an agent should read its standards file and the folder baseline.

## Workflow for agents

1. Identify the source file you are about to change.
2. Read the colocated `*.COMPONENT.md` next to that file.
3. Read the folder baseline `_BASE.md` in the same directory.
4. Read the layer baseline (`frontend/src/_BASE.md` or `backend/app/_BASE.md`).
5. Implement the change. Run through the verification checklist in the component doc before considering the change done.
6. If you are adding a new source module, create its `*.COMPONENT.md` in the same change using the shared template.

## File naming

| Source | Standards file |
|--------|----------------|
| `Foo.tsx` / `Foo.ts` / `Foo.css` | `Foo.COMPONENT.md` in the same directory |
| `foo.py` | `foo.COMPONENT.md` in the same directory |
| Any folder | One `_BASE.md` at the top of that folder |

## Shared template

Every `*.COMPONENT.md` follows this structure:

```markdown
# {ModuleName}

> Inherits: ./_BASE.md

## Purpose
One sentence: what this module owns in the product.

## Source
- Path: ...
- Layer: frontend-component | frontend-page | frontend-api | backend-router | ...

## Contract
- Exports / endpoints / props / request body / response shape

## Dependencies
- May import: explicit allow-list
- Must not: explicit denials

## Patterns (symmetry)
- Specific rules tied to existing code

## UI / UX (frontend only)
- Tailwind tokens, layout role, mobile vs desktop behaviour

## Verification checklist
- [ ] Concrete checks taken from the code
```

Folder `_BASE.md` carries the layer-wide rules so per-file docs only describe deltas, not the entire convention set every time.

## Baseline inventory

### Layer baselines

- [frontend/src/_BASE.md](frontend/src/_BASE.md)
- [backend/app/_BASE.md](backend/app/_BASE.md)

### Folder baselines (frontend)

- [frontend/src/api/_BASE.md](frontend/src/api/_BASE.md)
- [frontend/src/components/cards/_BASE.md](frontend/src/components/cards/_BASE.md)
- [frontend/src/components/common/_BASE.md](frontend/src/components/common/_BASE.md)
- [frontend/src/components/evidence/_BASE.md](frontend/src/components/evidence/_BASE.md)
- [frontend/src/components/layout/_BASE.md](frontend/src/components/layout/_BASE.md)
- [frontend/src/lib/_BASE.md](frontend/src/lib/_BASE.md)
- [frontend/src/pages/_BASE.md](frontend/src/pages/_BASE.md)
- [frontend/src/store/_BASE.md](frontend/src/store/_BASE.md)

### Folder baselines (backend)

- [backend/app/core/_BASE.md](backend/app/core/_BASE.md)
- [backend/app/db/_BASE.md](backend/app/db/_BASE.md)
- [backend/app/models/_BASE.md](backend/app/models/_BASE.md)
- [backend/app/routers/_BASE.md](backend/app/routers/_BASE.md)
- [backend/app/routers/v1/_BASE.md](backend/app/routers/v1/_BASE.md)
- [backend/app/schemas/_BASE.md](backend/app/schemas/_BASE.md)
- [backend/app/schemas/v1/_BASE.md](backend/app/schemas/v1/_BASE.md)
- [backend/app/seed/_BASE.md](backend/app/seed/_BASE.md)
- [backend/app/scripts/_BASE.md](backend/app/scripts/_BASE.md)
- [backend/app/services/_BASE.md](backend/app/services/_BASE.md)
- [backend/app/services/ir_discovery/_BASE.md](backend/app/services/ir_discovery/_BASE.md)
- [backend/app/services/ir_discovery/exchange/_BASE.md](backend/app/services/ir_discovery/exchange/_BASE.md)
- [backend/app/services/pipeline/_BASE.md](backend/app/services/pipeline/_BASE.md)
- [backend/app/workers/_BASE.md](backend/app/workers/_BASE.md)

## Cross-cutting product rules

These come from [README.md](README.md) and are referenced from individual standards docs:

- **Card colours (spec §11).** Positive, Negative, Mixed, Neutral, Low-confidence. Always include a text label — never colour alone.
- **Feed ranking (spec §19).** `card_priority` reflects financial materiality + severity + surprise + confidence + relevance. Honour the existing ordering when changing list views.
- **Pipeline.** `extracted_values → financial_statement_facts → calculated_metrics → generated_signals → intelligence_cards → card_evidence`. Do not introduce shortcuts that skip a layer. The real ingestion implementation lives under [backend/app/services/pipeline/](backend/app/services/pipeline/_BASE.md) and is the only package that writes those tables outside the seed.
- **Ingestion runtime.** [`backend/app/routers/ingest.py`](backend/app/routers/ingest.py) accepts uploads and enqueues `extraction_jobs`. The worker in [`backend/app/workers/`](backend/app/workers/_BASE.md) drains the queue and runs `services/pipeline/runner.run_pipeline_for_document`. The standalone bulk path [`backend/app/scripts/bulk_ingest.py`](backend/app/scripts/bulk_ingest.COMPONENT.md) (driven by [`services/ir_discovery/`](backend/app/services/ir_discovery/_BASE.md)) reaches the same end-state for a date / quarter / last-N range. Bulk discovery is two-tier: tier-1 [`services/ir_discovery/exchange/`](backend/app/services/ir_discovery/exchange/_BASE.md) hits the BSE / NSE corporate-filings APIs; tier-2 (`agent.find_period_assets`) only runs for asset slots tier-1 left empty, and is gated by `--no-agent-fallback`. `Company.bse_code` is backfilled by [`backend/app/scripts/resolve_bse_codes.py`](backend/app/scripts/resolve_bse_codes.COMPONENT.md). Both paths share helpers in [`services/ingest_common.py`](backend/app/services/ingest_common.COMPONENT.md). Auto-publish is gated on `AUTO_PUBLISH_CONFIDENCE`; below that, the Review Queue keeps the cards unpublished until an admin approves via `PATCH /review/{id}`.
- **Production-only data.** There is no demo seed and no prefilled credentials. The catalog seeder [seed_catalog.py](backend/app/seed/seed_catalog.py) only writes reference data (line items, metric and signal definitions, financial periods, sectors). An optional single admin user is bootstrapped from `ADMIN_EMAIL` / `ADMIN_PASSWORD` env vars; otherwise users come from `POST /auth/signup`.

## Maintenance rules

- A new `*.tsx` or `*.py` module must be added together with its `*.COMPONENT.md`.
- When a file is renamed, rename its standards file in the same change.
- When a public contract changes (props, route, response model), update the **Contract** section and **Verification checklist** in the colocated doc.
- Do not put secrets in standards files. Reference [backend/.env.example](backend/.env.example) instead.
