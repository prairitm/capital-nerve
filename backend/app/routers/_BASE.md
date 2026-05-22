# `backend/app/routers/` baseline

> Inherits: [../_BASE.md](../_BASE.md)

One module per HTTP resource. Routers own SQL, authentication, response shaping, and route-local validation.

## Conventions

- Each router file declares exactly one `router = APIRouter(prefix="/...", tags=["..."])`.
- Register the router in [`../main.py`](../main.py) — there is no auto-discovery.
- The flat routers in this folder are the legacy `/cards`, `/signals`, `/events`, `/companies`, etc. surface. The v1 enterprise namespace lives in [`v1/`](v1/_BASE.md) and is registered in `../main.py` alongside the flat routers.
- Standard dependency signature for authenticated endpoints:

  ```python
  def endpoint(
      ...,
      db: Session = Depends(get_db),
      user: AppUser = Depends(get_current_user),
  ) -> ...:
  ```

  Admin endpoints replace `get_current_user` with `get_current_admin`.
- Use `response_model=...` whenever the return type is a Pydantic model or `list[...]` thereof. Routes that return ad hoc dicts (company / event detail, search) call `.model_dump(...)` on their building blocks before returning.
- Build payloads via [`_helpers.py`](_helpers.py) (`company_brief`, `period_brief`, `card_brief`, `build_source_label`, `find_company`). Do not duplicate the mapping logic in individual routers.
- Heavier enrichment (calculated metrics, trend sparklines, concall heatmaps, signal context) is delegated to [`../services/`](../services/).
- Query parameters use FastAPI's `Query(...)` with explicit bounds (`ge=1, le=200`) where pagination applies — match the existing card / signal limits.
- Use `Literal[...]` for tab/filter values shared with the frontend (see [`cards.py`](cards.py)) so OpenAPI documents them as enums.

## SQL style

- Build queries with `sqlalchemy.select(...)`, `.join(...)`, `.outerjoin(...)`, `.where(...)`, `.order_by(...)`, `.limit(...)`. Execute via `db.scalar`, `db.scalars`, or `db.execute(...).all()`.
- For card / signal listings the canonical join is `IntelligenceCard → Company → FinancialPeriod (outer) → CompanyEvent (outer) → SourceDocument (outer)`. Reuse this shape (`cards.list_cards` is the reference).
- Use `is_(True)` / `is_(None)` rather than `== True` for boolean / null comparisons.

## Errors

- `HTTPException(status_code=404, detail="...")` for missing resources.
- `HTTPException(status_code=400, detail="...")` for client-side errors (duplicate signup, etc.).
- Auth errors are already handled by `get_current_user` / `get_current_admin`; do not raise 401 from a route body.

## Adding an endpoint

1. Decide which existing router owns the resource. Create a new router file only for a genuinely new resource and register it in `main.py`.
2. Build the response shape in [`../schemas/common.py`](../schemas/common.py) if it is shared, or as a local Pydantic model in the router for one-off bodies.
3. Mirror the TypeScript shape in [`../../../frontend/src/api/types.ts`](../../../frontend/src/api/types.ts) before wiring the client.
