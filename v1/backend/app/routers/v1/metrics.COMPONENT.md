# metrics

> Inherits: ./_BASE.md

## Purpose
Expose the seeded `MetricDefinition` rows as a typed read-only catalog so the frontend can render a metric-registry drawer and inline "definition" links on metric chips.

## Source
- Path: backend/app/routers/v1/metrics.py
- Layer: backend-router

## Contract
- `GET /v1/metrics/registry` -> `MetricRegistryResponse` — every metric with formula, expected range, inputs, dependencies, and the signals that reference it (walked from `signal_definitions.rule_json`).
- `GET /v1/metrics/registry/{metric_code}` -> `MetricRegistryEntry` — single-metric lookup for tooltip / drawer.

## Dependencies
- May import: `app.models.intelligence.MetricDefinition`, `app.models.intelligence.SignalDefinition`, `app.schemas.v1.metrics`, `app.core.deps`.
- Must not: write metric definitions (those live in `app.seed.seed_catalog`).

## Patterns (symmetry)
- Mirrors `app.routers.v1.signals` shape: one ORM model -> one builder helper (`_to_entry`) -> one paged endpoint.
- Sort order is `(metric_kind, metric_category, metric_code)` so the frontend can group financial / model / composite without re-sorting.

## Verification checklist
- [ ] `/v1/metrics/registry` returns every metric in `METRIC_DEFS` with kind populated.
- [ ] `/v1/metrics/registry/revenue_yoy_growth_acceleration_pp` returns kind=composite and lists `revenue_acceleration` under related_signals.
- [ ] Unknown metric_code -> 404.
