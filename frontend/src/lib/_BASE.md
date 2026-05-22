# `frontend/src/lib/` baseline

> Inherits: [../_BASE.md](../_BASE.md)

Pure helpers — no React, no router, no API calls.

## Rules

- Every export is a pure function. No side effects, no module-level state beyond constants.
- Do not import from `react`, `react-router-dom`, `react-query`, or `@/api/client`. Importing types from [`@/api/types`](../api/types.ts) is fine.
- Formatting helpers use Indian conventions: `toLocaleString("en-IN")`, ` Cr`, `L Cr`, `₹`. See [`format.ts`](format.ts).
- Null and `undefined` returns `"—"` (em dash). Keep the placeholder consistent — components depend on it.
- Card / timeline grouping helpers live in [`cards.ts`](cards.ts); add new feed transforms here, not inside pages.
- When a helper becomes the obvious source of truth for a UI rule (e.g. `mainIssueLabel` returns label tied to overall signal direction), call sites must use it rather than re-deriving locally.
