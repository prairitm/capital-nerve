# schemas/v1/signals

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Typed signal shapes for the v1 namespace. The flat `/signals` router still returns `dict[str, Any]`; v1 callers use these models so OpenAPI documents the contract.

## Source

- Path: `backend/app/schemas/v1/signals.py`
- Layer: backend-schemas

## Contract

- `SignalBriefV1` — compact row. Embedded inside `IntelligenceObject.signal` and returned by `GET /v1/signals` and `GET /v1/companies/{symbol}/signals`.
- `SignalDetailV1` (extends `SignalBriefV1`) — adds `description`, `rule_text`, `rule_json`, `calculation: SignalCalculation | None`, `metric_refs`, `evidence_refs`, `evidence: list[EvidenceItem]`. Returned by `GET /v1/signals/{id}`.
- `SignalCalculation` — `(metric_code, operator, threshold, current_value, previous_value, change_percent, change_bps, unit, rule_text)`. Sourced from `signal_definitions.rule_json` + `calculated_metrics`.

## Dependencies

- May import: `pydantic`, [`../../db/enums.py`](../../db/enums.py), [`../common.py`](../common.py) (`CompanyBrief`, `PeriodBrief`, `EvidenceItem`).
- Must not: import ORM models or routers/services.

## Patterns (symmetry)

- `SignalBriefV1` uses enum types directly (`SignalDirection`, `SeverityLevel`) — Pydantic serializes them by value.
- `SignalDetailV1.calculation` is the structured replacement for the legacy `rule_summary: str` field. Keep the legacy ad-hoc dict in the flat router; v1 callers should not depend on it.

## Verification checklist

- [ ] New field mirrored in [`../../../../frontend/src/api/types.ts`](../../../../frontend/src/api/types.ts)
- [ ] `SignalDetailV1` strict superset of `SignalBriefV1`
- [ ] Optional nested objects use `| None = None`
