"""v1 feed summary schema.

Drives the home page's market pulse strip without exposing the legacy
`GET /cards/summary` dict shape.
"""

from __future__ import annotations

from pydantic import BaseModel


class FeedSummaryV1(BaseModel):
    """Counters used by the Market Intelligence Summary strip."""

    results_processed: int
    positive_signals: int
    negative_signals: int
    margin_warnings: int
    red_flags: int
    guidance_updates: int
    verdicts: int
    growth: int
    margins: int
    risks: int
