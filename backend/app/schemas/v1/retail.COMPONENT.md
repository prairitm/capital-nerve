# schemas/v1/retail

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Wire shape for `GET /v1/companies/{symbol}/retail-summary` — consumer brokerage wedge. A plain-language summary + risk + momentum + top 3 points + headline metrics.

## Source

- Path: `backend/app/schemas/v1/retail.py`
- Layer: backend-schemas

## Contract

- `RetailSummaryPoint` — `(label, tone, detail)`. Tone is one of `positive | negative | mixed | neutral`.
- `RetailSummary` — `(company, period, simple_summary, risk_level, momentum, top_3_points, headline_metrics)`.

## Dependencies

- May import: `pydantic`, [`../common.py`](../common.py).
- Must not: import ORM models or services.

## Patterns (symmetry)

- `simple_summary` is one sentence — meant for the retail stock page hero. It is the `one_line_summary` of the top published card for the company.
- `headline_metrics` is `list[dict]` with `name`, `value`, `unit` so renderers can show Revenue / EBITDA / PAT / Margin without knowing the metric codes.
- `momentum` derives from the modal `signal_direction` of the top six cards; `risk_level` from the max severity. Reuse this rule across consumers.

## Verification checklist

- [ ] Mirrored in [`../../../../frontend/src/api/types.ts`](../../../../frontend/src/api/types.ts)
- [ ] `top_3_points` has at most three entries and deduplicates by `card_type`
- [ ] `headline_metrics` items use `{name, value, unit}` keys exactly
