# models/events

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Event-side tables: `CompanyEvent` (the canonical "thing happened"), `SourceDocument`, `DocumentPage`, `ExtractionJob`.

## Source

- Path: `backend/app/models/events.py`
- Layer: backend-models

## Contract

- `CompanyEvent` — links a company (and optional period) to a typed event with overall verdict fields (`overall_signal`, `overall_severity`, `overall_confidence`, `summary_text`, `main_issue`, `watch_next`).
- `SourceDocument` — file metadata + extraction status (`PENDING / PROCESSING / COMPLETED / FAILED / NEEDS_REVIEW`). The `metadata` Python attribute maps to the SQL column name `metadata` (`mapped_column("metadata", JSONB)`).
- `DocumentPage` — one row per page with `page_text`, `page_markdown`, `layout_json`. Cascade-deleted with the source document.
- `ExtractionJob` — bookkeeping for the (future) real extraction pipeline.

## Dependencies

- Imports: SQLAlchemy primitives, `JSONB`, `Base`, enums (`AuditStatus`, `ConsolidationType`, `DocumentType`, `EventType`, `ExchangeCode`, `ExtractionStatus`, `SeverityLevel`, `SignalDirection`).

## Patterns (symmetry)

- `CompanyEvent.is_published` defaults `True`. Use `False` for ingestion drafts.
- `SourceDocument.file_hash` is uniquely indexed — use it for dedupe.
- `DocumentPage` uses `ondelete="CASCADE"` so deleting a source document removes its pages. Other tables (cards, evidence) intentionally do not cascade.
- The "verdict" fields on `CompanyEvent` mirror those on `IntelligenceCard`. When you change one, consider whether the other needs the same change.

## Verification checklist

- [ ] New verdict fields mirrored to `EventDetail` / `TimelineEvent` schemas
- [ ] `file_hash` uniqueness preserved
- [ ] Cascade rules unchanged on `DocumentPage`
- [ ] Alembic migration created for any column changes
