# models/review

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Admin review queue rows for ingestion validation and low-confidence extractions.

## Source

- Path: `backend/app/models/review.py`
- Layer: backend-models

## Contract

- `ReviewQueue` — links to `company_id`, `event_id`, `document_id`, `card_id`, `extracted_value_id` (all optional). Required fields: `review_type` (string), `priority` (`SeverityLevel`), `status` (default `"OPEN"`).
- Statuses used today: `"OPEN"`, `"APPROVED"`, `"REJECTED"`, `"CORRECTED"`. Keep the set aligned with the frontend admin actions.

## Dependencies

- Imports: SQLAlchemy primitives, `Base`, `SeverityLevel`.

## Patterns (symmetry)

- `review_type` is a free-text string today (`"new_document_ingested"`, future types). When you introduce a new type, document it in [`../routers/review.py`](../routers/review.py).
- `resolved_at` is set by the router when the status moves to `APPROVED / REJECTED / CORRECTED`.
- `assigned_to` is an optional FK to `AppUser` — admin tooling can set this.

## Verification checklist

- [ ] New status added to the frontend admin page allow-list
- [ ] `resolved_at` set on terminal transitions
- [ ] Alembic migration created when columns change
