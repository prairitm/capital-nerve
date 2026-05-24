# routers/v1/companies

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Typed company hub (`CompanyHubV1`) and the searchable company list that
replaces the legacy `GET /companies` and `GET /companies/{symbol}` blob
endpoints.

## Source

- Path: `backend/app/routers/v1/companies.py`
- Prefix: `/v1`
- Tags: `["v1: companies"]`
- Layer: backend-router (v1)

## Endpoints

- `GET /v1/companies?search=&sector=&limit=` — returns `list[CompanyBrief]`.
- `GET /v1/companies/{symbol}` — returns `CompanyHubV1` with badges, latest
  event verdict, top intelligence objects, financial snapshot,
  8-quarter trends, event timeline, and source documents.

## Dependencies

- May import: ORM models, `_helpers.company_brief` / `period_brief` /
  `find_company`, `services.event_summary`,
  `services.intelligence_object_builder.build_intelligence_object_brief`,
  schemas in `schemas/common` and `schemas/v1`.
- Must not: build raw dict payloads or import the legacy `companies.py`
  router.

## Patterns (symmetry)

- Latest event resolution prefers `QUARTERLY_RESULT`, then falls back to
  the most recent event of any type. The verdict / summary on the hub
  always come from `resolve_event_summary_text` so v1 stays in lockstep
  with the persisted summary.
- Top intelligence objects are filtered the same way as the cross-company
  feed (`is_published=True`, `card_type != 'watch_next'`) so the hub and
  the feed never disagree on what the user can see.
- Latest event resolution and the embedded timeline only include
  `CompanyEvent.is_published=True`, matching
  `GET /v1/companies/{symbol}/events`.
- Badges are derived from the latest event direction plus the card type of
  the top objects — mirrors the legacy logic in
  `app.routers.companies.company_detail`.

## Verification checklist

- [ ] `GET /v1/companies/{symbol}` returns HTTP 404 for unknown symbols.
- [ ] `latest_summary` falls back to the rebuild path when the stored
      summary is the pipeline placeholder.
- [ ] `top_objects` only contains published, non-`watch_next` cards.
- [ ] `timeline` and `latest_event_id` omit unpublished events (review queue).
- [ ] Snapshot rows include a YoY delta only when the prior-year quarter
      fact exists.
- [ ] `watchlist_status` reflects whether the current user has the company
      in their default watchlist.
