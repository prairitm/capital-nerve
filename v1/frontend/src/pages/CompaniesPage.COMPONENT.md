# CompaniesPage

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Browse all companies at `/companies` with a name/symbol filter. Each card links to the company detail page.

## Source

- Path: `frontend/src/pages/CompaniesPage.tsx`
- Route: `/companies`
- Layer: frontend-page

## Contract

- Data: `GET /companies?search=` (`CompanyBrief[]`).

## Dependencies

- May import: `react`, `react-router-dom` (`Link`), `@tanstack/react-query`, `lucide-react` (`Search`), `@/api/client`, `@/api/types`, `@/components/common/Spinner` (`PageLoader`), `@/lib/format` (`formatCr`).
- Must not: introduce a sort selector — the backend already orders by `company_name`.

## Patterns (symmetry)

- Search state lives in local `useState` and is included in the React Query key (`["companies", q]`).
- Link target: `/company/${c.nse_symbol || c.bse_code}` — same fallback chain used everywhere else.
- Card layout reuses `.card p-4 hover:border-line-strong block`.

## Verification checklist

- [ ] Search input has the leading `Search` icon
- [ ] Link target uses `nse_symbol || bse_code`
- [ ] Market cap rendered via `formatCr`
- [ ] React Query key includes the search string
