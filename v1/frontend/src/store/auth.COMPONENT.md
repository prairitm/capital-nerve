# store/auth

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Holds the authenticated user and access token, persists them across reloads via `localStorage`, and syncs token writes with [`@/api/client`](../api/client.ts) so HTTP requests pick up auth changes immediately.

## Source

- Path: `frontend/src/store/auth.ts`
- Layer: frontend-store

## Contract

- Exports `useAuthStore` (zustand hook).
- `AuthState`:
  - `user: UserPayload | null`
  - `token: string | null`
  - `setAuth(resp: TokenResponse): void`
  - `setUser(user: UserPayload | null): void`
  - `logout(): void`

## Dependencies

- May import: `zustand`, `zustand/middleware` (`persist`), `@/api/types`, `@/api/client` (`setToken`).
- Must not: import React components or React Router (the store must be safe to import from anywhere).

## Patterns (symmetry)

- `setAuth` and `logout` call `setToken(...)` from `@/api/client` to keep the HTTP client in sync with the persisted store.
- `persist` uses the key `"cn_auth"` (the `localStorage` token uses `"cn_token"` — two separate keys on purpose so the API client can detect the token cheaply without parsing JSON).
- Read minimal slices in components: `useAuthStore((s) => s.user)` rather than destructuring the whole store, except where multiple fields are genuinely needed (e.g. `AppShell`).

## Verification checklist

- [ ] `setAuth` calls `setToken(resp.access_token)` first, then updates the store
- [ ] `logout` clears both the token and the user state
- [ ] `persist` key is `"cn_auth"`
- [ ] No React or router imports
