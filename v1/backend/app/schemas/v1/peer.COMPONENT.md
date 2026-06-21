# schemas/v1/peer

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Wire shape for `GET /v1/companies/{symbol}/peer-narrative` — the IR / competitive intelligence wedge. Derived entirely from `concall_facts.topic` clusters; no new tables.

## Source

- Path: `backend/app/schemas/v1/peer.py`
- Layer: backend-schemas

## Contract

- `NarrativeTheme` — `(topic, count, sample_claim)`. Sourced from `concall_facts` grouped by `topic`.
- `PeerCompanyThemes` — `(company, themes)`. One row per same-sector peer.
- `PeerNarrativeComparison` — `(company, company_narrative, peer_narratives, positioning_gap, over_communicated_topics, under_communicated_topics)`.

## Dependencies

- May import: `pydantic`, [`../common.py`](../common.py) (`CompanyBrief`).
- Must not: import ORM models or services.

## Patterns (symmetry)

- `positioning_gap` is a short human-readable sentence derived in the service. Renderers should not try to re-derive it.
- `over_communicated_topics` and `under_communicated_topics` are sorted alphabetically so the response shape is stable across calls.

## Verification checklist

- [ ] Mirrored in [`../../../../frontend/src/api/types.ts`](../../../../frontend/src/api/types.ts)
- [ ] `peer_narratives` excludes the query company
- [ ] Themes are deduped via `Counter` (no inline `for` accumulator that double-counts)
