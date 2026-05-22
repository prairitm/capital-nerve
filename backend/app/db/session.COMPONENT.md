# db/session

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

SQLAlchemy engine and session factory.

## Source

- Path: `backend/app/db/session.py`
- Layer: backend-db

## Contract

- Exports:
  - `engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, future=True)`
  - `SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)`
  - `get_db()` generator — kept for historical reasons; **import the router-facing `get_db` from [`../core/deps.py`](../core/deps.py)** instead.

## Dependencies

- Imports `sqlalchemy.create_engine`, `sqlalchemy.orm.sessionmaker`, `app.core.config.settings`.

## Patterns (symmetry)

- Engine flags are intentional:
  - `pool_pre_ping=True` heals stale connections on serverless restarts.
  - `future=True` enforces the 2.0 API.
  - `expire_on_commit=False` lets routers return ORM objects after commit without re-querying.
- Do not add migration helpers here — those belong to Alembic.

## Verification checklist

- [ ] Routers import `get_db` from `app.core.deps`, not from here
- [ ] Engine settings unchanged unless the change is reviewed
- [ ] No connection-pool side effects (no `connect()` at module scope)
