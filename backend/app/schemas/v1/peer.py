"""Peer narrative comparison v1 schemas.

Derived from `concall_facts.topic` clusters across the company and its sector
peers. This is the IR / competitive intelligence wedge — it tells a company
which themes it is under-communicating compared with peers.
"""

from pydantic import BaseModel

from app.schemas.common import CompanyBrief


class NarrativeTheme(BaseModel):
    topic: str
    count: int
    sample_claim: str | None = None


class PeerCompanyThemes(BaseModel):
    company: CompanyBrief
    themes: list[NarrativeTheme] = []


class PeerNarrativeComparison(BaseModel):
    company: CompanyBrief
    company_narrative: list[NarrativeTheme] = []
    peer_narratives: list[PeerCompanyThemes] = []
    positioning_gap: str | None = None
    over_communicated_topics: list[str] = []
    under_communicated_topics: list[str] = []
