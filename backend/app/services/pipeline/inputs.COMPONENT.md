# services/pipeline/inputs

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Resolve a metric definition's declarative input list against
`financial_statement_facts` and earlier `calculated_metrics` for a single
`(company_id, period_id)`. The metric engine in [`metrics.py`](metrics.py)
uses this to feed the AST evaluator without a custom SQL block per metric.

## Source

- Path: `backend/app/services/pipeline/inputs.py`
- Layer: backend-service

## Contract

- `InputResolver(db, *, company_id, period_id).resolve(declarations) -> dict[str, float | None]`.
- `declarations` is a list of dicts with keys:
  - `name` — local variable name used in the formula.
  - `code` — the `normalized_code` (or metric code, see `kind`).
  - `scope` — one of `CURRENT`, `PQ`, `PY`, `PY_PQ`, `TTM`, `TTM_AVG`,
    `AVG_2_OPENING_CLOSING`. Default `CURRENT`.
  - `kind` — `"fact"` (default) reads from `financial_statement_facts`;
    `"metric"` reads from earlier `calculated_metrics` rows so a metric can
    depend on another metric (`fcf` → `cfo - capex_ppe - capex_intangibles`).
- Missing inputs return `None`; the formula evaluator short-circuits the
  whole metric to `None`. Never raises on missing data — partial documents
  are normal.

## Scope semantics

| Scope | Meaning |
|-------|---------|
| `CURRENT` | Same period the metric is being computed for. |
| `PQ` | One quarter earlier (rolls fy_year when `quarter == 1`). |
| `PY` | Prior year, same quarter. |
| `PY_PQ` | Prior-year prior quarter (used for 4-quarter lag comparators). |
| `TTM` | Sum of the last four quarters (CURRENT + 3 priors). Returns `None` if any quarter is missing. |
| `TTM_AVG` | Average over the same window. |
| `AVG_2_OPENING_CLOSING` | (CURRENT + PY) / 2 — opening-balance / closing-balance averages for asset-turnover style metrics. |

## Dependencies

- May import: `app.models.facts`, `app.models.intelligence`,
  `app.models.master`, `sqlalchemy`.
- Must not import: routers, LLM modules, formula evaluator (the resolver is
  consumed by metrics.py, not the other way round).

## Patterns (symmetry)

- One resolver instance per pipeline run. Lookups are cached by
  `(kind, period_id, code)` so repeated metrics in the same run hit the DB
  once per quarter.
- `_SUPPORTED_SCOPES` is the single source of truth — extend it when adding
  a new scope, and update [`tests/test_seed_config.py`](../../../tests/test_seed_config.py).

## Verification checklist

- [ ] `CURRENT` lookup matches `period_value_type='CURRENT'` rows only.
- [ ] `PQ` rolls fy_year correctly when `quarter == 1`.
- [ ] `TTM` returns `None` if any of the four quarters is missing.
- [ ] `kind="metric"` reads only metrics already written for the period —
      relies on the metrics stage doing `db.flush()` per metric.
- [ ] Unknown scope → resolver logs a warning and returns `None`.
