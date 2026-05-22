# SaveWatchItemDialog

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Modal dialog for creating a `UserWatchItem` from a card. Lets the user override the title and description, set a threshold and a comparison operator, and submit.

## Source

- Path: `frontend/src/components/cards/SaveWatchItemDialog.tsx`
- Layer: frontend-component (smart — owns its own mutation)

## Contract

- Export: `export function SaveWatchItemDialog(props: Props)`
- Props (`interface Props`):
  - `open: boolean`
  - `onClose: () => void`
  - `companyId: number | null` — submit is disabled when `null`.
  - `defaultTitle: string`
  - `defaultDescription?: string`
  - `cardId?: number | null`

## Dependencies

- May import: `react`, `@tanstack/react-query`, `lucide-react` (`X`), `@/api/client`.
- Must not: bypass the React Query cache for the watchlist (`["watchItems"]`).

## Patterns (symmetry)

- Mutates `POST /watch-items` with body `{ company_id, card_id, title, description, target_value, condition_operator, condition_json }`.
- On success: `qc.invalidateQueries({ queryKey: ["watchItems"] })` and `onClose()`.
- Resets local title / description state from props in a `useEffect` that depends on `defaultTitle` and `defaultDescription`.
- Operator options are `"<"`, `">"`, `"<="`, `">="` (matches backend `condition_operator` strings — keep the four symbols aligned).
- Buttons: `btn-secondary` (Cancel) and `btn-primary` (Save). Failure renders an inline `text-negative` message.

## UI / UX

- Z-index `z-[60]` — must sit above the card detail drawer (`z-50`).
- Backdrop: `bg-black/60 backdrop-blur-sm`. Container: `.card p-5` inside `max-w-md`.
- Labels use `text-xs text-ink-mute mb-1 block`; inputs use `.input`.

## Verification checklist

- [ ] `open === false` returns `null`
- [ ] Mutation invalidates `["watchItems"]` on success
- [ ] Submit disabled while pending or when required fields (`companyId`, `title`) are missing
- [ ] Operator strings match the backend (`<`, `>`, `<=`, `>=`)
- [ ] No direct `fetch` calls — uses `api()` only
