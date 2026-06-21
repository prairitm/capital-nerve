# routers/admin

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Admin maintenance: onboard new issuers and bulk-purge every company and dependent intelligence row.

## Source

- Path: `backend/app/routers/admin.py`
- Prefix: `/admin`
- Tags: `["admin"]`
- Layer: backend-router (admin)

## Endpoints

- `GET /admin/sectors` — sector picker for the ingest "new company" form.
- `POST /admin/companies` — body `CreateCompanyRequest`; creates `Company` + optional `Security` (NSE).
- `POST /admin/clear-all-companies` — removes **every** company and all dependent rows (events, documents, facts, metrics, signals, cards, evidence, watchlists, alerts). Keeps sectors, periods, definitions, and users.

## Dependencies

- May import: ORM models, `app.routers._helpers.company_brief`.
- Must not: import pipeline stages directly or anything from `app.seed.seed_demo` (file removed; only `seed_catalog` exists).

## Patterns (symmetry)

- All routes use `get_current_admin`.
- The purge helper deletes rows in dependency order so foreign keys never block.
- NSE symbols are uppercased on create; duplicates return HTTP 400.

## Verification checklist

- [ ] `POST /admin/clear-all-companies` returns `companies_removed > 0` when companies exist and `0` on an empty DB.
- [ ] `POST /admin/companies` returns 201 with `company` brief payload.
- [ ] After clear, `/v1/companies` returns an empty list.
- [ ] Ingest upload for a newly created company completes without `uq_financial_facts` errors.
