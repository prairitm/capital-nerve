# CalculationChainPanel

> Inherits: ./_BASE.md

## Purpose

Render the structured Signal → Metric → Inputs evidence chain attached to every
`IntelligenceObject`, so an analyst can see precisely **why** a card fired and
trace each input back to the underlying document quote / page.

## Source

- Path: `frontend/src/components/evidence/CalculationChainPanel.tsx`
- Layer: frontend-component

## Contract

Props:

```ts
{
  chain: CalculationChain | null | undefined;
  className?: string;
}
```

`CalculationChain` is defined in [`@/api/types`](../../api/types.ts) and built
on the backend by
[`services/intelligence_object_builder._build_calculation_chain`](../../../../backend/app/services/intelligence_object_builder.py).
Returns `null` when neither a signal nor metric chain is present.

## Dependencies

- May import: `@/api/types`, `@/components/common/SourceDocumentLink`,
  `@/lib/format`, `lucide-react`, `clsx`.
- Must not: refetch evidence, call APIs, or compute formulas client-side. Every
  numeric and provenance value comes from the API payload.

## Patterns (symmetry)

- Sits **above** the existing "How we computed this" collapsible on
  `IntelligenceObjectPage` and inside `CardDetailDrawer` — never as a
  replacement, since the collapsible still carries raw `calculation_steps`.
- Uses the same `SourceDocumentLink` and italic-quote treatment as the rest of
  the evidence folder.
- Operator display uses the same vocabulary as
  `services/pipeline/signals._evaluate_rule` (`>`, `>=`, `<`, `<=`, `==`, `!=`).
- Scope labels mirror `services/pipeline/inputs.InputResolver` (`CURRENT`,
  `PQ`, `PY`, `PY_PQ`, `TTM`, `TTM_AVG`, `AVG_2_OPENING_CLOSING`).

## UI / UX

- Three vertically stacked `card-2` blocks (Signal, Metric, Inputs).
- Rule and formula text rendered in `font-mono` with a soft `surface-2` chip
  so the math reads cleanly against body copy.
- Quarantined metrics surface an inline `AlertTriangle` chip + the
  `quarantine_reason` string so the analyst sees why the value was suppressed.
- Source quotes use the standard `border-l-2 border-line pl-3 italic`
  treatment from the evidence baseline.

## Verification checklist

- [ ] Returns `null` if both `chain.signal` and `chain.metric` are absent.
- [ ] Renders `signal.rule_text`, `operator`, `fired_value` and either the
      `metric_ref` or numeric `threshold` for the signal row.
- [ ] Renders `metric.formula_text` with the resolved value on the same line.
- [ ] When `metric.is_quarantined` is true, shows the warning chip and the
      `quarantine_reason` string (if any).
- [ ] Each input row shows the formula symbol, scope label, value with unit,
      optional source quote, and a `SourceDocumentLink` to the document page.
- [ ] Uses `formatValueWithUnit` for both metric and input values so units
      stay consistent with the rest of the app (`%`, `bps`, `x`, `crore`).
