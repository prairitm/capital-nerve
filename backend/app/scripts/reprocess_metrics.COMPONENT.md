# scripts/reprocess_metrics

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Re-run the deterministic part of the ingestion pipeline (normalize → metrics
→ signals → cards) over already-persisted `extracted_values` without
calling the LLM provider. Used after Phase 1A of the analyst-trust
overhaul ships so existing RELIANCE / other-company cards pick up the new
unit rescaling and metric-output sanity bounds.

## Source

- Path: `backend/app/scripts/reprocess_metrics.py`
- Layer: backend-script

## CLI

```bash
python -m app.scripts.reprocess_metrics --all
python -m app.scripts.reprocess_metrics --company RELIANCE
python -m app.scripts.reprocess_metrics --document 42
```

Exactly one of `--all`, `--company`, `--document` is required.

## Behaviour

1. Loads every `ExtractedValue` for the target document(s).
2. Builds a transient `ExtractedLineItem` per row and runs
   `validators.canonicalize_units` against it. Lakh / million / billion /
   raw-rupee values are rescaled onto crore in place; the canonical unit
   string is written back to `extracted_values.unit`.
3. Calls `normalization.run_normalization`,
   `metrics.run_metrics`, `signals.run_signals`, `cards.run_cards`,
   `cards.run_result_verdict` in order — same as the runner, minus the
   LLM call and minus any extractor that needs the document storage
   bytes.
4. Quarantined metrics (values outside `metric_definitions.validation_min`
   / `validation_max`) are persisted with `is_quarantined=True` but never
   reach the signals stage.

## Dependencies

- May import: `app.db.session`, `app.models.*`,
  `app.services.event_summary`, `app.services.pipeline.{normalization, metrics, signals, cards, validators}`.
- Must not: call any LLM provider, touch document storage bytes, or
  re-parse PDFs. Reprocess is a deterministic replay of stages 2-5 only.

## Verification checklist

- [ ] `python -m app.scripts.reprocess_metrics --all` runs without
      raising on a fresh DB seed.
- [ ] Re-running twice in a row is idempotent — counts are stable.
- [ ] After reprocess, no `intelligence_cards` row references a metric
      with `metric_value` outside `metric_definitions.validation_*`.
- [ ] Failures are logged per document; the script continues to the next
      document instead of aborting the whole run.
