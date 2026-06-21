"""Stable numeric IDs bridging v2 string keys to the int IDs the UI expects.

The v1 frontend keys rows and routes by integer IDs, while the v2 store uses
string document IDs (`doc_*`) and ticker/period tuples. This module produces
deterministic integers so a card clicked in the feed resolves to the same
object on its detail page across requests.
"""

from __future__ import annotations

import hashlib


def stable_int(*parts: object) -> int:
    """Deterministic positive 31-bit int from the given parts.

    Kept under 2^31 so it round-trips cleanly through JSON and JS numbers used
    as React keys and route params.
    """
    key = "|".join(str(p) for p in parts)
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 2_000_000_000


def company_id(ticker: str) -> int:
    return stable_int("company", ticker.upper())


def period_id(ticker: str, quarter: int, fy_start_year: int) -> int:
    return stable_int("period", ticker.upper(), quarter, fy_start_year)


def event_id(ticker: str, quarter: int, fy_start_year: int) -> int:
    return stable_int("event", ticker.upper(), quarter, fy_start_year)


def document_id(doc_str: str) -> int:
    return stable_int("document", doc_str)


def object_id(ticker: str, quarter: int, fy_start_year: int, card_type: str) -> int:
    return stable_int("object", ticker.upper(), quarter, fy_start_year, card_type)


def signal_id(ticker: str, quarter: int, fy_start_year: int, signal_key: str) -> int:
    return stable_int("signal", ticker.upper(), quarter, fy_start_year, signal_key)
