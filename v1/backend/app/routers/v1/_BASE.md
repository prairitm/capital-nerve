# `backend/app/routers/v1/` baseline

> Inherits: [../_BASE.md](../_BASE.md)

The v1 enterprise API. Every router file declares `APIRouter(prefix="/v1", tags=["v1: ..."])` and is registered explicitly in [`../../main.py`](../../main.py) after the flat routers. All v1 endpoints are auth-gated.

## Modules

- [`events.py`](events.py) — `GET /v1/companies/{symbol}/events`, `GET /v1/events/{id}` (typed `EventBriefV1` / `EventDetailV1`).
- [`signals.py`](signals.py) — `GET /v1/companies/{symbol}/signals`, `GET /v1/signals`, `GET /v1/signals/{id}` (typed `SignalBriefV1` / `SignalDetailV1`).
- [`intelligence_objects.py`](intelligence_objects.py) — `GET /v1/companies/{symbol}/intelligence-objects`, `GET /v1/intelligence-objects`, `GET /v1/intelligence-objects/{id}`. The canonical decision-package endpoints.
- [`portfolio.py`](portfolio.py) — `POST /v1/portfolio/monitor`. Enterprise portfolio wedge.
- [`sectors.py`](sectors.py) — `GET /v1/sectors/{sector_name}/signals`. Cross-company roll-up.
- [`peers.py`](peers.py) — `GET /v1/companies/{symbol}/peer-narrative`. IR / competitive wedge.
- [`credit.py`](credit.py) — `GET /v1/companies/{symbol}/credit-risk-signals`. Bank / NBFC wedge.
- [`retail.py`](retail.py) — `GET /v1/companies/{symbol}/retail-summary`. Brokerage wedge.
- [`result_brief.py`](result_brief.py) — `GET /v1/companies/{symbol}/result-brief`. Sell-side analyst wedge.

## Rules

- All endpoints use `response_model=...` so OpenAPI documents the contract precisely. No ad-hoc `dict[str, Any]` returns — that pattern lives in the flat routers and should not be carried into v1.
- Symbol resolution always goes through [`../_helpers.find_company`](../_helpers.py). Company/period briefs go through `company_brief` / `period_brief`.
- Intelligence Object responses **must** go through [`../../services/intelligence_object_builder.py`](../../services/intelligence_object_builder.py). The list helpers (`build_intelligence_object_brief`) and the full builder (`build_intelligence_object`) are the single derivation point for `importance_score`, `time_horizon`, `investor_relevance`, `suggested_actions`, and `display`. Do **not** assemble these fields inline.
- Enterprise wedges (`portfolio`, `peers`, `credit`, `retail`, `result_brief`) delegate to the matching service module under [`../../services/`](../../services/). Routers stay thin (find company → call service → return).
- Filters use `Literal`/enum query parameters where the value set is known (e.g. `SignalDirection`, `SeverityLevel`). Use `Query(...)` with bounds for pagination (`ge=0`, `le=200`).
- Reuse the canonical join shape `IntelligenceCard → Company → FinancialPeriod (outer) → CompanyEvent (outer) → SourceDocument (outer)` for any new IO listing — see `intelligence_objects.list_intelligence_objects`.

## Adding a new v1 endpoint

1. Decide which existing v1 module owns the resource; create a new file only for a genuinely new wedge.
2. Add the wire shape in [`../../schemas/v1/`](../../schemas/v1/) and update its `_BASE.md`.
3. Push the actual computation into a service under [`../../services/`](../../services/).
4. Mirror the TS shape in [`../../../../frontend/src/api/types.ts`](../../../../frontend/src/api/types.ts) before wiring the client.
5. Register the router in [`../../main.py`](../../main.py).
