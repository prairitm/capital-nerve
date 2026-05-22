# `frontend/src/components/common/` baseline

> Inherits: [../../_BASE.md](../../_BASE.md)

Reusable, presentational building blocks: badges, spinners, source links, and empty states. These appear everywhere — keep them strict and minimal.

## Hard rules

- **Presentational only.** No `useQuery`, `useMutation`, or `api()` calls in this folder. Anything that needs data should accept it as a prop.
- **Single-purpose.** One component (or a tightly related pair like `Spinner` + `PageLoader`, `SourceDocumentLink` + `SourceDocumentLinks`) per file.
- **Null-safe.** Return `null` early when the required prop is missing — see [`SignalBadge.tsx`](SignalBadge.tsx) and [`ConfidenceBadge.tsx`](ConfidenceBadge.tsx).

## Badges (`SignalBadge`, `SeverityBadge`, `ConfidenceBadge`)

- Map enum values from [`@/api/types`](../../api/types.ts) to `{ label, klass }` using a top-level `Record` (pattern in `SignalBadge.tsx`).
- Always render a text label alongside the colour — spec §11. Use the `.chip-positive`, `.chip-negative`, `.chip-mixed`, `.chip-neutral`, `.chip-low` classes defined in [`@/styles.css`](../../styles.css).
- Support `size?: "sm" | "md"` for badges that appear in both feed-density and detail-density contexts.

## Source links (`SourceDocumentLink`, `SourceDocumentLinks`)

- All evidence links point at `/documents/:documentId` with optional `?page=` query. Build the href via `documentSourceHref()` from `SourceDocumentLink.tsx`; do not construct URLs ad hoc.
- When listing multiple evidence rows, dedupe with `uniqueSourceRefs(evidence, primary)`.

## Spinners and empty states

- Use `Spinner` for inline loading inside buttons; use `PageLoader` for full-page loading inside pages and the drawer.
- `Empty` is the canonical zero-state card — pages and panels should reuse it rather than rolling their own.
