# Frontend baseline

Layer-wide conventions for everything under `frontend/src/`. Each folder `_BASE.md` and per-file `*.COMPONENT.md` may add to these rules but must not contradict them.

## Stack

- Vite 5 + React 18 + TypeScript (strict)
- TailwindCSS 3 (dark theme) — global utility layer in `styles.css`
- `@tanstack/react-query` v5 for server state
- `zustand` (with `persist`) for client state — used only for auth in [`store/auth.ts`](store/auth.ts)
- `react-router-dom` v6 for routing
- `lucide-react` for icons, `recharts` for charts, `clsx` for conditional classes

## Imports

- Always use the `@/` path alias for files under `src/`. Reserve relative imports for sibling files in the same module (e.g. `main.tsx` → `./App`, `./styles.css`).
- Import order: third-party, then `@/api/...`, then `@/components/...`, then `@/lib/...`, then `@/store/...`.

## Exports

- Use named function exports: `export function Foo()` for components and pages. The only default export is [`App.tsx`](App.tsx) because Vite/router conventions expect it.
- Types and interfaces are exported as named exports too.

## Styling

- Tailwind utilities first. Reuse `.card`, `.card-2`, `.btn`, `.btn-primary`, `.btn-secondary`, `.btn-ghost`, `.chip-*`, `.input`, `.kbd`, `.ui-link`, `.ui-dot`, `.num` from [`styles.css`](styles.css).
- Use `clsx` for conditional class names; do not hand-concat class strings.
- Colour tokens come from [`tailwind.config.ts`](../tailwind.config.ts): `bg`, `bg-deep`, `surface`, `surface-2`, `line`, `line-strong`, `ink`, `ink-mute`, `ink-soft`, signal colours `positive`, `negative`, `mixed`, `neutral`.
- Card colours follow spec §11 — always pair colour with a label, never colour alone.

## Server state

- Every backend call goes through `api<T>()` in [`api/client.ts`](api/client.ts). Do not call `fetch` directly.
- `useQuery` / `useMutation` belong in pages and smart components (e.g. [`CardDetailDrawer.tsx`](components/cards/CardDetailDrawer.tsx)). Presentational components in `components/common/` and `components/cards/` (other than the drawer) receive data via props.
- Mutations call `queryClient.invalidateQueries({ queryKey: [...] })` instead of refetching manually.
- The global `QueryClient` is configured once in [`main.tsx`](main.tsx); do not create another.

## Domain types

- All shared API types live in [`api/types.ts`](api/types.ts). Do not redefine `CardBrief`, `CompanyBrief`, etc. in components.
- Inline interfaces are fine for local component props (`interface Props { ... }`).

## Formatting helpers

- Number, currency, percent, and date formatting goes through [`lib/format.ts`](lib/format.ts) (`formatNumber`, `formatCr`, `formatPct`, `formatSigned`, `formatDate`, `relativeDate`, `cardTypeLabel`, `eventTypeLabel`, `mainIssueLabel`, `timelineDateKey`).
- Feed filter, sort, and grouping logic goes through [`lib/cards.ts`](lib/cards.ts) (`filterInsightListCards`, `sortCardsByTime`, `groupCardsByEvent`, `groupCardsByTimeline`).

## Routing & auth

- Public routes are `/login` and `/signup`. Everything else is wrapped in `RequireAuth` + `AppShell` in [`App.tsx`](App.tsx).
- Auth state comes from `useAuthStore()` in [`store/auth.ts`](store/auth.ts). On 401 the API client clears the token and redirects to `/login`.

## Accessibility & UX

- Clickable non-button elements need `role="button"`, `tabIndex={0}`, and an `onKeyDown` Enter/Space handler. Pattern is in [`IntelligenceCard.tsx`](components/cards/IntelligenceCard.tsx).
- Nested buttons inside a click target use `e.stopPropagation()`.
- Mobile layouts use the bottom nav from [`AppShell.tsx`](components/layout/AppShell.tsx); pages do not add their own bottom nav.
