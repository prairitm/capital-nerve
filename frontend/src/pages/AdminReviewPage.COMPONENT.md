# AdminReviewPage

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Admin-only review queue at `/admin/review`. Lists pending extractions and low-confidence items with Approve / Reject actions.

## Source

- Path: `frontend/src/pages/AdminReviewPage.tsx`
- Route: `/admin/review`
- Layer: frontend-page (admin)

## Contract

- Data: `GET /review` or `GET /review?status_filter=OPEN` (admin only). Enabled only when `user?.user_type === "ADMIN"`. Response includes `signal_diagnostics`, `pipeline_stages`, and `publish_blocked_reasons`.
- Drill-down: `GET /review/:id/pipeline` when the user expands **Show pipeline details** on a card (`queryKey: ["review-pipeline", reviewId]`).
- Mutations: `PATCH /review/:id` with body `{ status }` where status ∈ `{ "APPROVED", "REJECTED", "CORRECTED", ... }`.

## Dependencies

- May import: `@tanstack/react-query`, `react-router-dom` (`Navigate`), `@/api/client`, `@/api/types`, `@/components/common/Spinner` (`PageLoader`), `@/components/common/SeverityBadge`, `@/store/auth`.
- Must not: surface admin-only data on non-admin sessions.

## Patterns (symmetry)

- Page guard: `if (user && user.user_type !== "ADMIN") return <Navigate to="/" replace />;`.
- React Query is `enabled: user?.user_type === "ADMIN"`.
- Mutation invalidates `["review"]` on success.
- **Approve** only when `status === "OPEN"`. **Reject** is also available on auto-published / `RESOLVED` / `APPROVED` rows (`Reject & unpublish` with confirm) so admins can pull bad jobs out of the feed after the fact.
- Approve / Reject call `PATCH /review/:id` with `"APPROVED"` or `"REJECTED"` — aligned with the backend allow-list.

## UI / UX

- Card list (one `.card` per review item) with pipeline stage chips, signal fired count, blocked-reason callout, and expandable **pipeline details** (extracted values, facts, metrics, signals, cards, full rule evaluation tables).
- Open / All filter toggles `status_filter=OPEN` on the query key.
- "Queue is clear." message when the open filter returns zero rows.

## Verification checklist

- [ ] Non-admin users redirected to `/`
- [ ] Query enabled only when user is admin
- [ ] Mutation invalidates `["review"]`
- [ ] Status strings (`APPROVED`, `REJECTED`) match backend `review.update_review`
- [ ] Reject available on `RESOLVED` / auto-published items with confirm dialog
- [ ] No drawer or modal — actions are inline buttons
