# services/signal_context

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Enrichment for signal detail responses: related cards, related signals, trigger metric, evidence, rule summary, and document brief.

## Source

- Path: `backend/app/services/signal_context.py`
- Layer: backend-service

## Contract

- `enrich_signal_detail(db, signal, definition, company, sector, period) -> dict[str, Any]` — produces the full payload the signal router returns.
- Adds: `rule_summary` (simple or composite tree), `rule_metric_codes`, `rule_leaves` (pass/fail per leaf), `primary_metric`, sorted `metric_comparisons`, `trigger_metric`.
- Internal helpers: `_format_rule`, `_format_rule_tree`, `_collect_rule_metric_codes`, `_build_rule_leaves`, `_load_related_cards`, related-signal lookup, evidence loader.

## Dependencies

- Imports: `sqlalchemy.select` / `or_`, models (`CompanyEvent`, `SourceDocument`, `CardEvidence`, `GeneratedSignal`, `IntelligenceCard`, `SignalDefinition`, `Company`, `FinancialPeriod`, `Sector`), helper `card_brief`, schemas (`DocumentBrief`, `EvidenceItem`), service (`load_metric_comparisons`, `load_trend_sparklines` from `card_context`).

## Patterns (symmetry)

- Rule summary: `_format_rule` for simple leaves; `_format_rule_tree` for `all` / `any` composite rules. Reuse `_op_label` for operator English.
- `rule_leaves` merge `GeneratedSignal.metric_refs` with rule JSON thresholds and `metric_comparisons` for display values.
- Related cards are filtered through the same `IntelligenceCard.is_published.is_(True)` and built via `card_brief`.
- Trigger metric: first `metric_refs` entry, else rule leaf `metric`, else first `rule_metric_codes` entry.
- Trends and metric comparisons reuse the card context helpers — do not duplicate the query.

## Verification checklist

- [ ] `_format_rule` / `_format_rule_tree` used for rule labels (no inline operator strings)
- [ ] Composite rules produce `rule_leaves` with `passed` when value + threshold known
- [ ] Related cards built via `card_brief`
- [ ] Trigger metric resolved from `metric_refs` or rule metric codes
- [ ] Trends / comparisons reuse `card_context` helpers
