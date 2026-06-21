# Backend baseline

Layer-wide conventions for everything under `backend/app/`.

## Stack

- FastAPI (`>=0.115,<0.120`) with `create_app()` factory in [`main.py`](main.py)
- SQLAlchemy 2.0 (sync) with `DeclarativeBase` in [`db/base.py`](db/base.py)
- Pydantic v2 schemas in [`schemas/`](schemas/)
- PostgreSQL via `psycopg` 3, JSON storage via `JSONB`
- JWT auth with `python-jose`, password hashing via `passlib[bcrypt]`
- Alembic for migrations (single initial revision)

## Module layout

- `core/` — settings, security, dependency injection wiring.
- `db/` — declarative base, session factory, shared Python enums backing Postgres enum types.
- `models/` — SQLAlchemy ORM models grouped by domain (`master`, `events`, `facts`, `intelligence`, `user`, `review`). `models/__init__.py` re-exports everything so Alembic can discover all tables.
- `schemas/` — Pydantic DTOs; `common.py` holds shared response shapes, `auth.py` holds signup/login/user.
- `routers/` — one module per HTTP resource; all `APIRouter` instances are registered explicitly in `main.py`.
- `services/` — read-only query helpers reserved for card / signal detail enrichment.
- `seed/` — the idempotent demo seeder.

## Routing & DI

- Each router defines `router = APIRouter(prefix="/...", tags=[...])`. Routes use snake_case Python names but expose REST-shaped URLs (`/cards`, `/companies/{symbol}`, `/auth/login`).
- Every authenticated route declares `db: Session = Depends(get_db), user: AppUser = Depends(get_current_user)` from [`core/deps.py`](core/deps.py). Use this exact spelling so type checkers and code search work.
- Admin-only routes use `admin: AppUser = Depends(get_current_admin)` instead.
- `get_db` is imported from `app.core.deps`. A duplicate exists in `app/db/session.py` for historical reasons — do not import it from there.

## Data access

- Use `sqlalchemy.select()` plus `db.scalar()` / `db.scalars()` / `db.execute()`. No `Query` API.
- Multi-table joins go directly in the router (see [`routers/cards.py`](routers/cards.py)). Helper functions in [`routers/_helpers.py`](routers/_helpers.py) (`company_brief`, `period_brief`, `card_brief`, `build_source_label`, `find_company`) build the response payloads.
- Heavier enrichment (calculated metrics, trend sparklines, concall heatmaps, signal context) belongs in [`services/`](services/) and is invoked from the router.

## Schemas & responses

- Declare a `response_model=...` on routes that return Pydantic models. Routes that return ad hoc dicts (e.g. `companies.company_detail`) call `.model_dump(...)` explicitly before returning.
- Do not blanket-enable `from_attributes` / ORM mode. Map ORM objects to schemas through the helpers in `_helpers.py` so nullability and casting (`float(Numeric)`) are explicit.
- New shared shapes go in `schemas/common.py`. Auth-specific shapes stay in `schemas/auth.py`. Request bodies that are local to one endpoint may stay inline (see `ingest.py`, `watch_items.py`, `review.py`).

## Errors

- Raise `HTTPException(status_code=..., detail="...")` from the route or dependency. Use 400 for client validation, 401 for auth failure, 403 for forbidden, 404 for missing resource.
- There is no global exception handler; do not introduce one without aligning the frontend `ApiError` handling.

## Enums

- All Postgres enum types live in [`db/enums.py`](db/enums.py) and are imported by models. When adding a new enum value:
  1. Add it to the Python enum.
  2. Add an Alembic migration to alter the Postgres enum.
  3. Update [`frontend/src/api/types.ts`](../../frontend/src/api/types.ts) so the union literal matches.

## Pipeline rule

The data flow is:

```
extracted_values → financial_statement_facts → calculated_metrics → generated_signals → intelligence_cards → card_evidence
```

Do not introduce shortcuts that skip a layer (for example, generating a card without a corresponding signal).
