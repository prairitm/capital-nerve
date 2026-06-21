# schemas/v1/credit

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Wire shape for `GET /v1/companies/{symbol}/credit-risk-signals` — credit monitoring wedge for banks / NBFCs. A filtered slice of `generated_signals` bucketed into credit dimensions.

## Source

- Path: `backend/app/schemas/v1/credit.py`
- Layer: backend-schemas

## Contract

- `CreditDimension` — `Literal["debt", "coverage", "working_capital", "earnings_quality", "auditor", "rating", "other"]`.
- `CreditRiskSignal` — `SignalBriefV1`-shaped row plus `credit_dimension`.
- `CreditRiskResponse` — `(company, overall_risk, rationale, signals)`.

## Dependencies

- May import: `pydantic`, [`../../db/enums.py`](../../db/enums.py), [`../common.py`](../common.py).
- Must not: import ORM models.

## Patterns (symmetry)

- `overall_risk` is the highest severity among NEGATIVE / MIXED matching signals. Render with `SeverityBadge` (label + colour).
- `credit_dimension` is derived in [`../../services/credit_risk.py`](../../services/credit_risk.py) via a `signal_code → dimension` precedence map; do not add inline mappings in routers.

## Verification checklist

- [ ] Mirrored in [`../../../../frontend/src/api/types.ts`](../../../../frontend/src/api/types.ts)
- [ ] Only credit-relevant categories surface (the service filter excludes unrelated signals)
- [ ] `overall_risk` matches the highest severity among the returned `signals`
