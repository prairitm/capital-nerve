# routers/v1/peers

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

`GET /v1/companies/{symbol}/peer-narrative` — IR / competitive intelligence wedge. Compares the company's concall narrative themes with same-sector peers.

## Source

- Path: `backend/app/routers/v1/peers.py`
- Prefix: `/v1`
- Tags: `["v1: peers"]`
- Layer: backend-router

## Endpoints

- `GET /v1/companies/{symbol}/peer-narrative` (`response_model=PeerNarrativeComparison`).

## Dependencies

- Imports: `fastapi`, models (`AppUser`), helpers (`find_company`), schemas (`PeerNarrativeComparison`), service (`build_peer_narrative`).
- Must not: hold its own SQL. Theme clustering lives in [`../../services/peer_narrative.py`](../../services/peer_narrative.py).

## Patterns (symmetry)

- Thin router — find company → delegate to service.
- Peers are resolved by `sector_id` match in the service (same convention as `result_brief_builder.py`).

## Verification checklist

- [ ] Symbol resolved via `find_company`
- [ ] No SQL in router body
- [ ] `response_model=PeerNarrativeComparison`
