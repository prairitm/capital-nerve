# metrics

> Inherits: ./_BASE.md

## Purpose
Pydantic schemas for the metric-registry API. Every metric definition the pipeline computes against is exposed here so the analyst-trust strip can answer "what kind of number is this and how is it calculated".

## Source
- Path: backend/app/schemas/v1/metrics.py
- Layer: backend-schema

## Contract
- `MetricRegistryEntry` — full definition: code, name, category, kind, unit, formula, bounds, inputs, deps, related_signals.
- `MetricRegistryInput` — `{name, code, scope, kind}` mirroring `MetricDefinition.inputs_json`.
- `MetricRegistrySignal` — signal_code / signal_name / rule_text for every signal whose `rule_json` references this metric.
- `MetricRegistryResponse` — `{metrics: list[MetricRegistryEntry]}` wrapper for the list endpoint.

## Dependencies
- May import: `pydantic`.
- Must not: depend on ORM models or DB sessions.

## Patterns (symmetry)
- Mirrors the shape of `app.models.intelligence.MetricDefinition`; new metric fields must land here too.

## Verification checklist
- [ ] `metric_kind` enum stays `financial | model_score | composite` in lockstep with the seed and migration 0007.
- [ ] `validation_min` / `validation_max` are nullable so unbounded metrics serialise cleanly.
