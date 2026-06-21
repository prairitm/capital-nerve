# services/pipeline/presentation

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Stage 1h. Regex extractor for investor-presentation slides: TAM, mix shift,
client/region concentration, capacity utilization, and management targets.

## Source

- Path: `backend/app/services/pipeline/presentation.py`
- Layer: backend-service

## Contract

- `is_investor_presentation_document(document) -> bool`
- `run_presentation_extraction(db, *, document, event) -> int`

## Verification checklist

- [ ] Only runs on ``INVESTOR_PRESENTATION`` document type.
- [ ] Metrics ``tam_growth_pct``, ``mix_shift_bps``, etc. reference seeded codes.
