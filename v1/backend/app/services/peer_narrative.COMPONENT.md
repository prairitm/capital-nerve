# services/peer_narrative

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Backs `GET /v1/companies/{symbol}/peer-narrative`. Clusters `concall_facts.topic` for the company and its same-sector peers, and computes which themes the company is over- or under-communicating.

## Source

- Path: `backend/app/services/peer_narrative.py`
- Layer: backend-service

## Contract

- `build_peer_narrative(db, company: Company) -> PeerNarrativeComparison`.

Module-level constants:

- `_PEER_LIMIT = 4` — max peers used in the comparison.
- `_TOP_THEMES = 6` — max themes per company.

## Dependencies

- Imports: `collections.Counter`, `sqlalchemy.select`, models (`ConcallFact`, `Company`), helpers (`company_brief`), schemas (`NarrativeTheme`, `PeerCompanyThemes`, `PeerNarrativeComparison`).

## Patterns (symmetry)

- Topic strings are stripped and skipped when empty so the clustering ignores `None` / blank topics.
- `positioning_gap` is a short sentence — either "X is under-communicating ..." or "X is leaning into ...". When neither set is non-empty, `positioning_gap` is `None`.
- Peers come from the same `sector_id` excluding the query company.

## Verification checklist

- [ ] Query company is not in `peer_narratives`
- [ ] Each peer has at least one theme (peers with empty narratives are dropped)
- [ ] `over_communicated_topics` / `under_communicated_topics` sorted alphabetically
- [ ] Returns a Pydantic model
