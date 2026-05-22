# `backend/app/db/` baseline

> Inherits: [../_BASE.md](../_BASE.md)

Database engine, session factory, declarative base, and the canonical Python enums backing Postgres enum types.

## Modules

- [`base.py`](base.py) — `class Base(DeclarativeBase)`. Every model inherits this.
- [`session.py`](session.py) — `engine` and `SessionLocal`. Holds a `get_db` generator for completeness, but routers must import `get_db` from [`../core/deps.py`](../core/deps.py).
- [`enums.py`](enums.py) — every shared enum. The Python class name doubles as the Postgres enum `name` parameter (e.g. `Enum(SignalDirection, name="signal_direction")`).

## Rules

- One declarative `Base` for the whole app. Do not create a second base.
- Engine settings (`pool_pre_ping=True`, `future=True`, `expire_on_commit=False`) are intentional — do not change them ad hoc.
- `enums.py` is the single source of truth for `SignalDirection`, `SeverityLevel`, `ConfidenceLevel`, `EventType`, `DocumentType`, `ExtractionStatus`, `UserType`, etc.
- When adding an enum value:
  1. Add it to the Python enum here.
  2. Generate an Alembic migration that runs `ALTER TYPE ... ADD VALUE ...`.
  3. Update the mirror in [`frontend/src/api/types.ts`](../../../frontend/src/api/types.ts).
- Do not put logic, helpers, or model imports in this folder — that would create circular imports against `models/`.
