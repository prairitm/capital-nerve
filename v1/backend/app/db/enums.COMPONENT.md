# db/enums

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Every Postgres-backed enum used by the app.

## Source

- Path: `backend/app/db/enums.py`
- Layer: backend-db

## Contract

- Each class subclasses `(str, enum.Enum)` so values serialize as strings.
- Enums defined: `ExchangeCode`, `CompanyStatus`, `EventType`, `DocumentType`, `StatementType`, `PeriodType`, `ConsolidationType`, `AuditStatus`, `SignalDirection`, `SeverityLevel`, `ConfidenceLevel`, `ExtractionStatus`, `UserType`.
- Postgres enum names used in `Enum(MyEnum, name="...")` declarations must match the lowercase snake-case version of the class name (e.g. `SignalDirection` → `"signal_direction"`).

## Dependencies

- Only `enum`. No SQLAlchemy / Pydantic imports.

## Patterns (symmetry)

- Mirror every change in [`frontend/src/api/types.ts`](../../../frontend/src/api/types.ts) so the TypeScript union stays in lockstep.
- When adding an enum value:
  1. Add it here.
  2. Generate an Alembic migration with `ALTER TYPE <name> ADD VALUE '<value>'`.
  3. Update the matching string-literal union in `frontend/src/api/types.ts`.
- Reuse existing enum names where possible (e.g. `SeverityLevel` is used by cards, signals, alerts, and review queue).

## Verification checklist

- [ ] Class subclasses `(str, enum.Enum)`
- [ ] Postgres `name=` matches the agreed snake-case
- [ ] Frontend mirror updated in the same change
- [ ] Alembic migration created for the new value
