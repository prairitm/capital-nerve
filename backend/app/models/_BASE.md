# `backend/app/models/` baseline

> Inherits: [../_BASE.md](../_BASE.md)

SQLAlchemy 2.0 ORM models, grouped by domain.

## Modules

- [`master.py`](master.py) — `Sector`, `Company`, `Security`, `FinancialPeriod`.
- [`events.py`](events.py) — `CompanyEvent`, `SourceDocument`, `DocumentPage`, `ExtractionJob`.
- [`facts.py`](facts.py) — extraction outputs and normalized facts (`ExtractedValue`, `FinancialLineItemDefinition`, `FinancialStatementFact`, segment / concall / presentation / announcement facts, `TranscriptChunk`, `AnalystQuestion`).
- [`intelligence.py`](intelligence.py) — `MetricDefinition`, `CalculatedMetric`, `SignalDefinition`, `GeneratedSignal`, `IntelligenceCard`, `CardEvidence`.
- [`user.py`](user.py) — `AppUser`, `Watchlist`, `WatchlistCompany`, `UserWatchItem`, `AlertRule`, `Alert`.
- [`review.py`](review.py) — `ReviewQueue`.
- [`__init__.py`](__init__.py) — re-exports every model for Alembic autogenerate.

## Rules

- Use the typed 2.0 style only: `Mapped[T]`, `mapped_column(...)`, `relationship(...)`. Avoid the legacy `Column(...)` API.
- Enums on columns spell the Postgres type name explicitly: `Enum(SignalDirection, name="signal_direction")`. Reuse names across tables that store the same enum.
- Use `JSONB` (from `sqlalchemy.dialects.postgresql`) for free-form JSON columns; default with `default=dict` or `default=list` as appropriate.
- Foreign keys cascade only when there is a clear ownership relationship — currently only `DocumentPage.document_id` and a few user-scoped tables use `ondelete="CASCADE"`. Preserve this on new tables; cards/signals/metrics are intentionally not cascaded so historical data survives doc deletion.
- Numeric financial values use `Numeric(24, 6)` for amounts, `Numeric(12, 4)` for percentages/bps, `Numeric(5, 2)` for confidence scores. Match these precisions when adding new columns.
- Timestamps use `DateTime(timezone=True)` with `server_default=func.now()` for `created_at`, plus `onupdate=func.now()` for `updated_at` where present.
- When you add a new model:
  1. Place it in the matching domain file (create a new file only for a genuinely new domain).
  2. Import and re-export it in `__init__.py`.
  3. Add an Alembic migration.
