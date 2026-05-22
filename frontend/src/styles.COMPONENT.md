# styles.css

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Global Tailwind layer plus the design-system component utility classes (`.card`, `.btn-*`, `.chip-*`, `.input`, etc.) that the rest of the app uses.

## Source

- Path: `frontend/src/styles.css`
- Layer: frontend-styling

## Contract

- Imported once from [`main.tsx`](main.tsx).
- Provides classes consumed everywhere; component files should not duplicate or override these.

## Class catalogue (canonical)

- Containers: `.card`, `.card-2`.
- Buttons: `.btn`, `.btn-primary`, `.btn-secondary`, `.btn-ghost`, `.btn-brand-active`.
- Inputs: `.input`.
- Chips: `.chip-positive`, `.chip-negative`, `.chip-mixed`, `.chip-neutral`, `.chip-low`.
- Misc: `.ui-link`, `.ui-icon`, `.ui-dot`, `.kbd`, `.num`, `.scrollbar-none`, `.prose-cn`.

## Rules

- Add new utilities only inside `@layer components { ... }`. Do not pollute the global CSS namespace.
- Reference colour tokens via Tailwind (`@apply bg-surface text-ink ...`); do not hardcode hex values inside the `@layer` block.
- Hex values live in `tailwind.config.ts` (and inside `recharts` stroke configs in [`MetricSparkline.tsx`](components/cards/MetricSparkline.tsx) / [`CompanyPage.tsx`](pages/CompanyPage.tsx)). Brand accent is blue (`#3B82F6` / `#60A5FA`); green is reserved for `positive` signals only.
- The background gradient on `body` is a deliberate brand accent. Do not remove without product sign-off.
- `font-feature-settings: "tnum" 1` on `.num` keeps financial numbers monospaced; reuse `.num` instead of inlining the feature setting.

## Verification checklist

- [ ] New classes added under `@layer components` only
- [ ] Colour references use Tailwind tokens, not hex values
- [ ] Component files reuse the catalogue instead of redefining equivalents
- [ ] `.num` used wherever a numeric value is rendered
