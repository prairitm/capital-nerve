# App

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Top-level route table. Wraps authenticated routes in `RequireAuth` + `AppShell` and provides a catch-all redirect to `/`.

## Source

- Path: `frontend/src/App.tsx`
- Layer: frontend-routing

## Contract

- Default export: `export default function App()`. This is the only default export in `src/`.
- Local `RequireAuth({ children })` reads `token` from `useAuthStore()`; missing token → `<Navigate to="/login" replace />`.

## Dependencies

- May import: `react-router-dom`, `@/components/layout/AppShell`, `@/pages/*`, `@/store/auth`.
- Must not: render `BrowserRouter` or `QueryClientProvider` — those belong to [`main.tsx`](main.tsx).

## Patterns (symmetry)

- Public routes (`/login`, `/signup`) sit at the top of the `<Routes>` block before the `RequireAuth` wrapper.
- Authenticated routes are nested inside a `<Route>` that renders `<RequireAuth><AppShell /></RequireAuth>`.
- Catch-all `<Route path="*" element={<Navigate to="/" replace />} />` lives at the end.
- When you add a new authenticated page, register it here and add the matching `NAV` entry in [`AppShell.tsx`](components/layout/AppShell.tsx).

## Verification checklist

- [ ] `RequireAuth` reads only the `token` field
- [ ] New pages added inside the nested `RequireAuth` group
- [ ] Catch-all redirect remains last
- [ ] No `QueryClient` instantiation here
