# routers/watch_items

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

CRUD for user-created "watch items" — thesis monitors with optional thresholds.

## Source

- Path: `backend/app/routers/watch_items.py`
- Prefix: `/watch-items`
- Tags: `["watch-items"]`
- Layer: backend-router

## Endpoints

- `GET /watch-items` — list current user's items.
- `POST /watch-items` — body `CreateWatchItem` with `company_id` (required), optional `card_id`, `metric_def_id`, `title`, `description`, `current_value`, `target_value`, `condition_operator`, `condition_json`.
- `PATCH /watch-items/{watch_item_id}` — body `UpdateWatchItem` (any subset). 404 if the item is not owned by the user.
- `DELETE /watch-items/{watch_item_id}` — 404 if not owned. Returns `{deleted: true}` on success.

## Dependencies

- Imports: `fastapi`, `pydantic.BaseModel`, `sqlalchemy.select`, models (`Company`, `UserWatchItem`, `AppUser`).

## Patterns (symmetry)

- `_to_payload(w, company)` is the canonical serializer (shared across list/create/update). Numeric casts and `created_at.isoformat()` live there.
- All mutations check ownership: `if not item or item.user_id != user.user_id: raise 404`. Preserve this rule — never 403 for not-owned items (mask existence).
- `PATCH` uses `model_dump(exclude_none=True)` so unset fields stay untouched.
- `condition_operator` values come from the frontend dialog: `<`, `>`, `<=`, `>=`.

## Verification checklist

- [ ] Ownership enforced as 404 (not 403)
- [ ] PATCH uses `exclude_none=True`
- [ ] Single serializer (`_to_payload`) used everywhere
- [ ] `condition_operator` allow-list aligned with the frontend dialog
