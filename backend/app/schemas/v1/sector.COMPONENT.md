# schemas/v1/sector

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Wire shape for the sector roll-up endpoint `GET /v1/sectors/{sector_name}/signals`. Same signal shape as the flat feed but the sector is the parent context.

## Source

- Path: `backend/app/schemas/v1/sector.py`
- Layer: backend-schemas

## Contract

- `SectorSignalRow` — compact signal row including `company` (with sector pre-resolved) and `period`.
- `SectorSignalsResponse` — `(sector_name, company_count, signal_count, signals)`.

## Dependencies

- May import: `pydantic`, [`../../db/enums.py`](../../db/enums.py), [`../common.py`](../common.py).
- Must not: import ORM models.

## Patterns (symmetry)

- `SectorSignalRow` deliberately keeps the same field names as `SignalBriefV1` so the frontend table can render either with a shared row component.
- `company_count` is the total companies in the sector; `signal_count` is the size of `signals` after filters. Renderers can show "X signals across Y companies".

## Verification checklist

- [ ] Mirrored in [`../../../../frontend/src/api/types.ts`](../../../../frontend/src/api/types.ts)
- [ ] `company_count` populated from `SELECT count(...)`, not `len(signals)`
