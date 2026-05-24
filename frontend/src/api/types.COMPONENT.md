# api/types

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

TypeScript shapes for every backend response and shared domain enum. Mirrors the Pydantic schemas in [`backend/app/schemas/common.py`](../../../backend/app/schemas/common.py) and [`backend/app/schemas/auth.py`](../../../backend/app/schemas/auth.py).

## Source

- Path: `frontend/src/api/types.ts`
- Layer: frontend-api

## Contract

- Pure type module — no runtime exports.
- Enums are string-literal unions (`SignalDirection`, `SeverityLevel`, `ConfidenceLevel`, `EventType`, `DocumentType`) that match [`backend/app/db/enums.py`](../../../backend/app/db/enums.py).
- Shared interfaces: `UserPayload`, `TokenResponse`, `CompanyBrief`, `PeriodBrief`, `CardBrief`, `CardDetail`, `EvidenceItem`, `CardMetricComparison`, `ConcernHeatmapRow`, `FeedSummary`, `CompanyBadge`, `TimelineEvent`, `FinancialSnapshotRow`, `FinancialTrend`, `FinancialTrendPoint`, `DocumentBrief`, `CompanyDetail`, `EventDetail`, `SignalRow`, `SignalDetail`, `SignalEventBrief`, `WatchlistResponse`, `WatchItem`, `AlertItem`, `SearchResult`, `DocumentSearchHit`, `AskRequest`, `AskResponse`, `AskCitation`, `DocumentDetail`, `ReviewItem`, `ReviewPipelineDetail` (+ nested `ReviewPipelineExtracted`, `ReviewPipelineFact`, `ReviewPipelineMetric`, `ReviewPipelineSignal`, `ReviewPipelineCard`, `ReviewPipelineJob`).

## Dependencies

- No imports.

## Patterns (symmetry)

- Field names are `snake_case` (matching backend JSON).
- Nullable values use `T | null`, not `T | undefined`.
- Optional fields (those marked with `= None` or absent in the Pydantic model) use `?:` only when truly optional on the wire; defaulted fields use `T | null` because the backend always sends them.
- Use `Pick<...>` for derived shapes (e.g. `related_signals` in `SignalDetail`) rather than redefining the subset.

## Verification checklist

- [ ] Every new backend response field is added here
- [ ] Enum literals match `backend/app/db/enums.py`
- [ ] No runtime code in this file (no helper functions)
- [ ] Field nullability matches the Pydantic schema
