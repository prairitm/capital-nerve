# `backend/app/schemas/v1/` baseline

> Inherits: [../_BASE.md](../_BASE.md)

The v1 namespace is the wire contract for the enterprise API surface
(`/v1/...`). It is purely additive on top of [`../common.py`](../common.py);
existing endpoints under `/cards`, `/signals`, `/events`, `/companies` keep
their current contracts unchanged.

## Modules

- [`events.py`](events.py) — `EventBriefV1`, `EventDetailV1`, `EventRawFacts`. Wire shape for `GET /v1/companies/{symbol}/events` and `GET /v1/events/{id}`.
- [`signals.py`](signals.py) — `SignalBriefV1`, `SignalDetailV1`, `SignalCalculation`. Typed replacements for the ad-hoc dicts returned by the flat `/signals` router.
- [`intelligence_object.py`](intelligence_object.py) — `IntelligenceObject` (full), `IntelligenceObjectBrief` (feed), `IODisplayConfig`, `IOMetric`. The centerpiece — every consumer (drawer, alert, API, Excel, LLM) reads this shape.
- [`portfolio.py`](portfolio.py) — `PortfolioMonitorRequest`, `PortfolioAlert`, `PortfolioMonitorResponse`. POST input + ranked alert output for the portfolio wedge.
- [`sector.py`](sector.py) — `SectorSignalRow`, `SectorSignalsResponse`. Cross-company sector roll-up.
- [`peer.py`](peer.py) — `PeerNarrativeComparison`, `PeerCompanyThemes`, `NarrativeTheme`. IR competitive intelligence shape.
- [`credit.py`](credit.py) — `CreditRiskSignal`, `CreditRiskResponse`. Credit-only signal slice for bank / NBFC monitoring.
- [`retail.py`](retail.py) — `RetailSummary`, `RetailSummaryPoint`. Consumer brokerage shape.
- [`result_brief.py`](result_brief.py) — `ResultBrief`, `ResultBriefPoint`, `ResultPeerComparison`. Sell-side analyst quarterly brief.

## Rules

- All schemas subclass `BaseModel`. Inherit the `pydantic` conventions from [`../_BASE.md`](../_BASE.md) — `[]` / `{}` defaults, enum-by-value serialization, no `from_attributes`.
- The canonical Intelligence Object lives in `intelligence_object.py`. Do **not** invent a parallel projection in another module — extend this one.
- `EventBriefV1` and `SignalBriefV1` are deliberately separate from the existing `EventDetail` / `SignalDetail` in [`../common.py`](../common.py) so the v1 contract can evolve without breaking the flat routers used by the existing pages.
- New fields on `IntelligenceObject` must also be added to the TS interface in [`../../../../frontend/src/api/types.ts`](../../../../frontend/src/api/types.ts) and the builder in [`../../services/intelligence_object_builder.py`](../../services/intelligence_object_builder.py).
- Imports inside the package should be absolute (`from app.schemas.v1.events import ...`). The package `__init__.py` re-exports public names for short import paths.

## Cross-cutting rules carried from the spec

- **Card colours (spec §11):** `IntelligenceObject.status` is the source of truth. Renderers must pair colour with label using the badge components.
- **Pipeline rule:** every v1 object must reference an underlying event + signal + card. Schemas may have optional nested fields when the model has nullable FKs (e.g. cards without a signal), but routers should aim to populate them.
