# SignupPage

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Public signup form at `/signup`. Creates an account and signs the user in immediately on success.

## Source

- Path: `frontend/src/pages/SignupPage.tsx`
- Route: `/signup` (public)
- Layer: frontend-page

## Contract

- Mutation: `POST /auth/signup` with `{ email, password, full_name }` returning `TokenResponse`.
- On success: `setAuth(resp)` then `navigate("/")`.

## Dependencies

- May import: `react`, `react-router-dom`, `lucide-react` (`ArrowRight`), `@tanstack/react-query`, `@/api/client`, `@/store/auth`, `@/api/types`, `@/components/common/Spinner`.
- Must not: bypass `setAuth`; submit without the required fields.

## Patterns (symmetry)

- Layout mirrors `LoginPage` for visual consistency (`min-h-screen flex flex-col items-center justify-center`, `card p-6 space-y-4`).
- Password `minLength={6}` matches the backend `Field(min_length=6)` in `SignupRequest`.
- Error rendering follows `LoginPage` ("(m.error as Error).message || 'Sign-up failed.'").

## Verification checklist

- [ ] Password minimum length matches backend (6)
- [ ] On success calls `setAuth` and navigates to `/`
- [ ] Submit disabled while pending
- [ ] No `AppShell` wrapper — the route is public
