# `frontend/src/api/` baseline

> Inherits: [../_BASE.md](../_BASE.md)

This folder is the only place that knows how to talk to the backend.

## Responsibilities

- `client.ts` exposes the single `api<T>(path, opts)` wrapper, token storage helpers, and the `ApiError` class.
- `types.ts` holds the TypeScript shape of every backend response. Names mirror the Pydantic models in [`backend/app/schemas/common.py`](../../../backend/app/schemas/common.py).

## Rules

- All HTTP requests in the app go through `api<T>()`. Do not call `fetch` from components, pages, or hooks.
- The API base path is `/api` (proxied to the FastAPI backend in `vite.config.js`). Do not hardcode `http://localhost:8000` anywhere.
- Token lifecycle: `setToken` is called by [`store/auth.ts`](../store/auth.ts) on login/logout; the client reads it via `getToken()`. Do not write to `localStorage["cn_token"]` directly.
- 401 responses clear the token and redirect to `/login`. Other non-2xx responses throw `ApiError`.
- When you add a new endpoint:
  1. Add the response interface to `types.ts`, matching the field names and nullability of the Pydantic schema.
  2. Use it via `api<NewType>("/path")` in the calling page/component.
  3. Do not export ad hoc fetch helpers — every call uses the same wrapper.

## Symmetry with backend

- Field names are `snake_case` because the backend serializes Pydantic models that way; TypeScript uses these names verbatim.
- Enums are mirrored as string-literal unions (`"POSITIVE" | "NEGATIVE" | ...`) and must match [`backend/app/db/enums.py`](../../../backend/app/db/enums.py).
- If you add a new enum value on the backend, update `types.ts` in the same change.
