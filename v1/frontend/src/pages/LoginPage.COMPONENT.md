# LoginPage

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Public sign-in form at `/login`. Empty form by default; redirects on success.

## Source

- Path: `frontend/src/pages/LoginPage.tsx`
- Route: `/login` (public)
- Layer: frontend-page

## Contract

- Mutation: `POST /auth/login` with `{ email, password }` returning `TokenResponse`.
- On success: `useAuthStore().setAuth(resp)` then `navigate(location.state?.from || "/", { replace: true })`.

## Dependencies

- May import: `react`, `react-router-dom` (`Link`, `useNavigate`, `useLocation`), `lucide-react` (`ArrowRight`, `Sparkles`), `@tanstack/react-query`, `@/api/client`, `@/store/auth`, `@/api/types`, `@/components/common/Spinner`.
- Must not: bypass `setAuth` — token storage is centralised in the auth store.

## Patterns (symmetry)

- Inputs start empty. The signup CTA below the form points new users to `/signup`. There are no demo or admin credentials in the UI.
- Form uses `<form onSubmit={...}>` and submits via `m.mutate()`. Submit button shows `Spinner` while pending.
- Error rendering uses `text-sm text-negative` and displays `(m.error as Error).message || "Sign-in failed."`.
- Standalone layout (no `AppShell`) — the page is centred on the viewport using `min-h-screen flex flex-col items-center justify-center`.

## Verification checklist

- [ ] Fields are empty on first render
- [ ] On success calls `setAuth` and navigates to `from` if present
- [ ] Submit disabled while pending
- [ ] Error message visible without leaking the raw `Error` object structure
- [ ] No `AppShell` wrapper — the route is public
- [ ] No demo or admin credentials referenced anywhere in the page
