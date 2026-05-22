# schemas/v1/feed

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Typed schema for the home page's market pulse strip, returned by
`GET /v1/intelligence-objects/summary`.

## Source

- Path: `backend/app/schemas/v1/feed.py`
- Layer: backend-schema (v1)

## Contract

- `FeedSummaryV1` fields (all `int`):
  - `results_processed`
  - `positive_signals`
  - `negative_signals`
  - `margin_warnings`
  - `red_flags`
  - `guidance_updates`
  - `verdicts`
  - `growth`
  - `margins`
  - `risks`

## Dependencies

- Imports only `pydantic.BaseModel`.

## Patterns (symmetry)

- Field names mirror the keys previously returned by the legacy
  `GET /cards/summary` dict so the frontend can swap the call without
  reshaping component props.
- `results_processed` and `verdicts` intentionally hold the same count
  (the count of `result_verdict` cards) so existing UI labels keep
  working.

## Verification checklist

- [ ] All ten counters present and typed `int`.
- [ ] Exported from `app.schemas.v1.__init__`.
