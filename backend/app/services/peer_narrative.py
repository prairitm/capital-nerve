"""Peer narrative comparison service.

Clusters `concall_facts.topic` for a company and its same-sector peers to
surface which narrative themes the company is over- or under-communicating.
"""

from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.facts import ConcallFact
from app.models.master import Company
from app.routers._helpers import company_brief
from app.schemas.v1.peer import (
    NarrativeTheme,
    PeerCompanyThemes,
    PeerNarrativeComparison,
)

_PEER_LIMIT = 4
_TOP_THEMES = 6


def _themes_for_company(db: Session, company_id: int) -> list[NarrativeTheme]:
    facts = db.scalars(
        select(ConcallFact)
        .where(ConcallFact.company_id == company_id)
        .where(ConcallFact.topic.is_not(None))
    ).all()
    if not facts:
        return []

    counter: Counter[str] = Counter()
    sample_by_topic: dict[str, str] = {}
    for fact in facts:
        topic = (fact.topic or "").strip()
        if not topic:
            continue
        counter[topic] += 1
        if topic not in sample_by_topic and fact.extracted_claim:
            sample_by_topic[topic] = fact.extracted_claim

    return [
        NarrativeTheme(topic=topic, count=count, sample_claim=sample_by_topic.get(topic))
        for topic, count in counter.most_common(_TOP_THEMES)
    ]


def build_peer_narrative(db: Session, company: Company) -> PeerNarrativeComparison:
    company_themes = _themes_for_company(db, company.company_id)

    peer_companies: list[Company] = []
    if company.sector_id is not None:
        peer_companies = db.scalars(
            select(Company)
            .where(Company.sector_id == company.sector_id)
            .where(Company.company_id != company.company_id)
            .limit(_PEER_LIMIT)
        ).all()

    peer_payloads: list[PeerCompanyThemes] = []
    peer_topic_counter: Counter[str] = Counter()
    for peer in peer_companies:
        themes = _themes_for_company(db, peer.company_id)
        if not themes:
            continue
        peer_payloads.append(PeerCompanyThemes(company=company_brief(peer), themes=themes))
        for theme in themes:
            peer_topic_counter[theme.topic] += theme.count

    company_topics = {theme.topic for theme in company_themes}
    peer_topics = set(peer_topic_counter.keys())

    over_communicated = sorted(company_topics - peer_topics)
    under_communicated = sorted(peer_topics - company_topics)

    gap: str | None = None
    if under_communicated:
        sample = under_communicated[:3]
        gap = (
            f"{company.short_name or company.company_name} is under-communicating "
            f"{', '.join(sample)} relative to peers."
        )
    elif over_communicated:
        sample = over_communicated[:3]
        gap = (
            f"{company.short_name or company.company_name} is leaning into "
            f"{', '.join(sample)} more than peers."
        )

    return PeerNarrativeComparison(
        company=company_brief(company),
        company_narrative=company_themes,
        peer_narratives=peer_payloads,
        positioning_gap=gap,
        over_communicated_topics=over_communicated,
        under_communicated_topics=under_communicated,
    )
