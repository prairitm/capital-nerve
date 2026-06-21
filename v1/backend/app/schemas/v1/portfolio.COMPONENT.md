# schemas/v1/portfolio

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Wire shapes for the portfolio monitoring wedge — `POST /v1/portfolio/monitor`. The request takes an arbitrary list of holdings; the response is ranked alerts each pointing at the underlying Intelligence Objects.

## Source

- Path: `backend/app/schemas/v1/portfolio.py`
- Layer: backend-schemas

## Contract

- `PortfolioMonitorRequest` — `symbols: list[str]` (max 200), optional `min_importance: int (0–100)`, optional `severity_in: list[SeverityLevel]`, optional `direction_in: list[SignalDirection]`, `limit_per_company: int (1–10, default 3)`.
- `PortfolioAlert` — `(company, matched, reason, top_objects: list[IntelligenceObjectBrief], triggered_at)`. `matched=False` rows show the company resolved but had no qualifying cards under the filters.
- `PortfolioMonitorResponse` — `(requested_symbols, resolved_companies, unresolved_symbols, alerts)`.

## Dependencies

- May import: `pydantic`, [`../../db/enums.py`](../../db/enums.py), [`../common.py`](../common.py), [`./intelligence_object.py`](intelligence_object.py).
- Must not: import ORM models or services.

## Patterns (symmetry)

- The endpoint surfaces unmatched symbols in `unresolved_symbols` rather than failing — this matches how enterprise consumers expect partial successes.
- `top_objects` reuses `IntelligenceObjectBrief` so the alert payload is self-contained (no follow-up fetch required for ranking).
- `reason` is a short human-readable summary derived from the top object; renderers should not derive their own (the service is the single source).

## Verification checklist

- [ ] Mirrored in [`../../../../frontend/src/api/types.ts`](../../../../frontend/src/api/types.ts) (`PortfolioMonitorRequest`, `PortfolioAlert`, `PortfolioMonitorResponse`)
- [ ] `symbols` bounded with `max_length=200`
- [ ] `min_importance` bounded with `ge=0`, `le=100`
- [ ] Alert list ordered: matched first, then by top-object `importance_score` desc
