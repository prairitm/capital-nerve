# `frontend/src/store/` baseline

> Inherits: [../_BASE.md](../_BASE.md)

Zustand is the only client-state library and it is used sparingly. Server data belongs in React Query, not here.

## Rules

- Today the only store is [`auth.ts`](auth.ts). Add a new store only when:
  1. The data is genuinely client-owned (not a server projection), and
  2. It needs to be shared across pages.
- Each store exports a typed hook (`export const useAuthStore = create<AuthState>()(...)`).
- Persisted stores use `persist(...)` middleware with a stable `name` key (`"cn_auth"` for auth). Pick keys with the `cn_` prefix.
- The auth store coordinates with [`@/api/client`](../api/client.ts): `setAuth` and `logout` call `setToken()` so the API client picks up the change without a re-render.
- Do not put server-derived collections (watchlist contents, feed items, alerts) in a store — those go through React Query so cache invalidation works.
