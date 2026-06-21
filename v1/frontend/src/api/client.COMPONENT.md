# api/client

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

The single HTTP entry point for the frontend. Provides the `api<T>()` wrapper, token storage helpers, and `ApiError`.

## Source

- Path: `frontend/src/api/client.ts`
- Layer: frontend-api

## Contract

- Exports:
  - `function getToken(): string | null`
  - `function setToken(token: string | null): void`
  - `class ApiError extends Error { status; detail }`
  - `function api<T>(path: string, opts?: RequestOpts): Promise<T>`
  - `function apiBlob(path: string, opts?: { signal?: AbortSignal }): Promise<Blob>` — authenticated binary GET (e.g. document PDFs)
- Internal: `TOKEN_KEY = "cn_token"`, `API_BASE = "/api"`, local `RequestOpts` interface.

## Dependencies

- Pure TS / DOM APIs only. No React, no router, no React Query.
- Must not: be replaced by direct `fetch` calls elsewhere — keep this file the single source of HTTP logic.

## Patterns (symmetry)

- `localStorage` access is wrapped in try/catch so SSR-like contexts do not throw.
- Request body is JSON unless absent; `Content-Type: application/json` is always set.
- Query params with `undefined`, `null`, or `""` values are skipped.
- 401 → `setToken(null)` + redirect to `/login` (unless already there) + throw `ApiError(401)`.
- Non-2xx → parse JSON `detail` string when present, else fall back to status text, throw `ApiError`.
- `signal: AbortSignal` is forwarded to `fetch` so React Query cancellation works.

## Verification checklist

- [ ] `TOKEN_KEY` remains `"cn_token"` (matches `store/auth.ts` persist key strategy)
- [ ] 401 handler clears the token and redirects to login
- [ ] Errors throw `ApiError` (never plain `Error`)
- [ ] All callers go through `api<T>()` — no raw `fetch` in the app
- [ ] Empty/undefined query values are dropped before serialization
