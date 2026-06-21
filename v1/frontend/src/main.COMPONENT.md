# main

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

React entry point. Mounts the app inside `BrowserRouter` + `QueryClientProvider` + `React.StrictMode` and imports the global stylesheet.

## Source

- Path: `frontend/src/main.tsx`
- Layer: frontend-bootstrap

## Contract

- No exports. Side-effect entry only.
- Mounts to `#root`.

## Dependencies

- Imports: `react`, `react-dom/client`, `react-router-dom` (`BrowserRouter`), `@tanstack/react-query`, `./App`, `./styles.css`.
- Uses relative imports for `./App` and `./styles.css` — these are intentional (Vite/TS expect them).

## Patterns (symmetry)

- Single `QueryClient` instance with defaults: `staleTime: 30_000`, `gcTime: 5 * 60_000`, `retry: 1`, `refetchOnWindowFocus: false`. Keep these unless you have a measured reason to change.
- Order of providers: `StrictMode` → `QueryClientProvider` → `BrowserRouter` → `<App />`.
- Do not introduce a second `QueryClient` anywhere else. Hooks call `useQueryClient()` to get the same instance.

## Verification checklist

- [ ] Exactly one `QueryClient` in the app
- [ ] React-Query defaults match the values above
- [ ] Provider nesting order preserved
- [ ] Global styles imported here, not in components
