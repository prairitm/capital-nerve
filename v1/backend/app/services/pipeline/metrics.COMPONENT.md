# services/pipeline/metrics

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Stage 3. Compute the calculated metrics that the rest of the system reads
through `calculated_metrics`. The implementation is config-driven: every
metric is declared in `metric_definitions` with `inputs_json`,
`formula_text`, and `dependencies_json`, and the runner walks the metric
DAG once per period — no per-metric Python.

## Source

- Path: `backend/app/services/pipeline/metrics.py`
- Layer: backend-service

## Contract

- `run_metrics(db, *, document) -> int` — for the document's
  `(company_id, period_id)`:
  1. Loads every `MetricDefinition` row.
  2. Topo-sorts them via `dependencies_json` so metric-of-metric formulas
     (`fcf → cfo`, `net_debt_to_ebitda → net_debt + ttm_ebitda`) are
     computed in the right order.
  3. For each definition: resolves inputs via [`InputResolver`](inputs.py),
     evaluates `formula_text` via [`formula.evaluate`](formula.py), persists
     a `CalculatedMetric` row including the input snapshot and a step trace.
  4. Persists comparison metadata (`comparison_period_id`, `change_absolute`,
     `change_percent`) when the metric has a `PY` or `PQ` comparator input,
     so the existing UI keeps showing trend chips.
  5. **Bounds quarantine.** Values outside `MetricDefinition.validation_min`
     / `validation_max` are persisted with `is_quarantined=True` and a
     human-readable `quarantine_reason`. Downstream signals load
     non-quarantined rows only — see [`signals._load_metric_values`](signals.py).

## Dependencies

- May import: `app.models.{intelligence,master,events}`,
  `app.services.pipeline.{formula,inputs}`.
- Must not import: LLM modules or other pipeline stages.

## Patterns (symmetry)

- Idempotent: previous metrics for `(company_id, period_id)` are deleted
  before insertion. Document re-ingest must overwrite. Because metrics are
  period-scoped (not document-scoped), `_clear_period_metric_dependents`
  removes `generated_signals` / `intelligence_cards` / `card_evidence` rows
  that still FK the old `metric_id` values (including cross-document signals)
  before the metric delete runs.
- Topo sort uses Kahn's algorithm; cycle detection logs an error and aborts
  the metrics stage rather than masking config bugs.
- Each metric is flushed (`db.flush()`) before the next one runs so the
  `kind="metric"` resolver can read it back.
- Missing inputs drop the metric, never raise.

## Verification checklist

- [ ] `metric_definitions.formula_text` matches `calculation_steps.formula`
      on each persisted row.
- [ ] Adding a new metric requires only a new entry in
      [`seed_catalog.METRIC_DEFS`](../../seed/seed_catalog.py); no code change here.
- [ ] `tests/test_seed_config.py` enforces "every formula parses" and
      "metric DAG is acyclic".
- [ ] Re-running the pipeline does not duplicate metric rows.
- [ ] Division-by-zero metrics are skipped silently.
- [ ] Values outside the metric's plausible bounds land on `calculated_metrics`
      with `is_quarantined=True` and never feed signals/cards.
