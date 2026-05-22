"""v1 enterprise API schemas — formally-typed projections of the existing pipeline.

The v1 namespace is the source of truth for the wire shape consumed by enterprise
integrations and the upgraded frontend Intelligence Object surface. It is purely
additive on top of `schemas/common.py`; existing routers keep their current
contracts unchanged.
"""

from app.schemas.v1.companies import CompanyHubV1
from app.schemas.v1.credit import CreditRiskResponse, CreditRiskSignal
from app.schemas.v1.events import EventBriefV1, EventDetailV1, EventRawFacts
from app.schemas.v1.feed import FeedSummaryV1
from app.schemas.v1.intelligence_object import (
    IntelligenceObject,
    IntelligenceObjectBrief,
    IODisplayConfig,
    IOMetric,
)
from app.schemas.v1.peer import NarrativeTheme, PeerCompanyThemes, PeerNarrativeComparison
from app.schemas.v1.portfolio import (
    PortfolioAlert,
    PortfolioMonitorRequest,
    PortfolioMonitorResponse,
)
from app.schemas.v1.result_brief import ResultBrief, ResultBriefPoint, ResultPeerComparison
from app.schemas.v1.retail import RetailSummary, RetailSummaryPoint
from app.schemas.v1.sector import SectorSignalRow, SectorSignalsResponse
from app.schemas.v1.signals import SignalBriefV1, SignalCalculation, SignalDetailV1

__all__ = [
    "CompanyHubV1",
    "CreditRiskResponse",
    "CreditRiskSignal",
    "EventBriefV1",
    "EventDetailV1",
    "EventRawFacts",
    "FeedSummaryV1",
    "IntelligenceObject",
    "IntelligenceObjectBrief",
    "IODisplayConfig",
    "IOMetric",
    "NarrativeTheme",
    "PeerCompanyThemes",
    "PeerNarrativeComparison",
    "PortfolioAlert",
    "PortfolioMonitorRequest",
    "PortfolioMonitorResponse",
    "ResultBrief",
    "ResultBriefPoint",
    "ResultPeerComparison",
    "RetailSummary",
    "RetailSummaryPoint",
    "SectorSignalRow",
    "SectorSignalsResponse",
    "SignalBriefV1",
    "SignalCalculation",
    "SignalDetailV1",
]
