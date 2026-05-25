# services/pipeline/signals

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Stage 4. Evaluate `signal_definitions.rule_json` against the metrics just
written by [`metrics`](metrics.py) and emit `GeneratedSignal` rows. The
rule grammar supports composite boolean rules — `all`, `any`, `not`, plus
metric-vs-threshold and metric-vs-metric leaves — so cross-card signals
(`dirty_beat`, `low_quality_growth`, `value_trap`, `governance_red_flag`,
`turnaround`, `narrative_mismatch`) are configuration, not code.

## Source

- Path: `backend/app/services/pipeline/signals.py`
- Layer: backend-service

## Contract

- `run_signals(db, *, document) -> tuple[list[GeneratedSignal], SignalDiagnostics]`.
- `evaluate_signal_rules(db, *, document) -> {"diagnostics": ..., "candidates": ...}` —
  dry run used by the review queue when job meta lacks diagnostics.
- Rule grammar:
  - **Leaf**: `{"metric": "<code>", "operator": ">|>=|<|<=|==|!=", "threshold": <num>}`
    or `{"metric": "<code>", "operator": "...", "metric_ref": "<other_metric>"}`.
  - **Composite**: `{"all": [<rule>, ...]}`, `{"any": [<rule>, ...]}`,
    `{"not": <rule>}`. Backwards-compatible with the legacy single-leaf seeds.
- Signals without any numeric rule (`management_caution`, `audit_redflag`)
  are intentionally **not** generated here — they require concall fact /
  auditor-note extractors that are a separate pipeline stage.

## Dependencies

- May import: `app.models.{intelligence,events}`.
- Must not import: LLM modules.

## Patterns (symmetry)

- Re-runs delete `card_evidence` / `intelligence_cards` for `document_id`,
  then existing signals, before inserting fresh ones — cards FK `signal_id`
  and the cards stage runs after signals.
- `metric_refs` on `GeneratedSignal` records every leaf the rule tree
  touched, including the operator + threshold; the drawer reads this to
  render "Why this fired" copy.
- Severity escalation: when the headline leaf's breach exceeds 2× threshold,
  severity bumps from `MEDIUM → HIGH`; large absolute breaches (≥ 500) on
  non-margin categories may bump `HIGH → CRITICAL`. Mirror this rule if you
  add a new severity escalation.
- `primary_metric_id` is populated whenever the rule has a metric reference
  so the drawer's "primary metric" badge reads it back directly.

## Verification checklist

- [ ] Re-runs do not duplicate signals.
- [ ] Re-runs with existing cards do not hit `intelligence_cards_signal_id_fkey`.
- [ ] Each emitted signal references a real `CalculatedMetric` via
      `primary_metric_id` and `metric_refs[0].metric_id`.
- [ ] Composite rules with a missing metric anywhere in the tree report
      `metric_missing` in diagnostics, not a crash.
- [ ] Backwards compat: legacy `{"metric": ..., "operator": ..., "threshold": ...}`
      rules still fire on the same values that fired them in v1 (covered by
      `tests/test_signal_eval.py`).
- [ ] `metric_ref` comparisons use the live value of the comparator metric,
      not the seed thresholds.
