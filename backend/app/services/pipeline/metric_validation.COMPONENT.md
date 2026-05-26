# metric_validation

> Inherits: ./_BASE.md

## Purpose
Run cross-statement, recompute-drift, and extreme-growth checks on the
``calculated_metrics`` written for a single (company, period) so the
runner can block auto-publish on internally inconsistent extractions.

## Source
- Path: `backend/app/services/pipeline/metric_validation.py`
- Layer: backend-pipeline

## Contract
- `validate_calculated_metrics(db, *, company_id, period_id) -> MetricValidationReport`
- `apply_validation_actions(db, *, company_id, period_id, report) -> int` —
  quarantines metrics with recompute drift **or** extreme growth before signal
  evaluation
- `MetricValidationReport` exposes `cross_statement_breaches`,
  `recompute_drift`, and `growth_review` lists plus `to_dict()` for
  persistence on `ExtractionJob.meta['metric_validation']`. Growth-review
  rows carry `comparator` (`"yoy"` / `"qoq"`) so the review queue can label
  what gate they failed.

## Dependencies
- May import: SQLAlchemy `Session`, models in `app.models.facts` and
  `app.models.intelligence`.
- Must not: write to the DB, mutate `CalculatedMetric` rows, or import
  the runner / cards stages (cyclical).

## Patterns (symmetry)
- Mirrors the stage-report pattern used by
  `validators.ValidatorReport` and `metric_anomaly.AnomalyReport`.
- Tolerances are module-level constants (`_RECOMPUTE_DRIFT_PP`,
  `_GROWTH_REVIEW_PCT_YOY`, `_GROWTH_REVIEW_PCT_QOQ`) so they can be tuned
  in one place. QoQ uses a tighter gate than YoY because QoQ swings of
  ±100 % almost always indicate a YTD-vs-PQ column-tag mismatch.
- ``apply_validation_actions`` mutates ``CalculatedMetric`` rows (quarantine +
  confidence downgrade on drift / extreme growth); the runner calls it
  before signals so quarantined rows never reach `_load_metric_values`.
- The runner also blocks auto-publish when ``recompute_drift`` is non-empty,
  when ``unit_rescaled`` touches a fired signal's primary-metric inputs
  (from ``job.validator_report``), or when cross-statement / growth gates fire.

## Verification checklist
- [ ] PAT > Revenue and EBITDA > Revenue both produce
      `cross_statement_breaches` entries.
- [ ] A stored `pat_margin` that drifts more than 2 pp from
      `pat / revenue * 100` shows up in `recompute_drift`.
- [ ] QoQ growth metrics with `|value| > 100 %` and YoY growth metrics with
      `|value| > 300 %` produce `growth_review` entries even when bounds
      pass, and `apply_validation_actions` quarantines them so signals skip
      them.
- [ ] `runner.run_pipeline_for_document` calls this module after
      `metrics_stage.run_metrics` and persists the report under
      `ExtractionJob.meta['metric_validation']`.
