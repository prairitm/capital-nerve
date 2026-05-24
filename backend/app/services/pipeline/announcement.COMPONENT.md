# services/pipeline/announcement

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Stage 1g. Regex extractor for press-release disclosures: new orders, M&A
value, dividend per share, revenue contribution %, and capacity figures.

## Source

- Path: `backend/app/services/pipeline/announcement.py`
- Layer: backend-service

## Contract

- `is_press_release_document(document) -> bool`
- `run_announcement_extraction(db, *, document, event) -> int`

## Verification checklist

- [ ] Only runs on ``PRESS_RELEASE`` document type.
- [ ] New codes exist in ``seed_catalog.LINE_ITEMS`` before use.
