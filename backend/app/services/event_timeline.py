"""Canonical company event timelines — one row per reporting period."""

from __future__ import annotations

from app.db.enums import EventType
from app.models.events import CompanyEvent

_EVENT_TYPE_RANK: dict[EventType, int] = {
    EventType.QUARTERLY_RESULT: 0,
    EventType.ANNUAL_REPORT: 1,
    EventType.INVESTOR_PRESENTATION: 2,
    EventType.CONCALL_TRANSCRIPT: 3,
    EventType.PRESS_RELEASE: 4,
    EventType.EXCHANGE_FILING: 5,
    EventType.SHAREHOLDING_PATTERN: 6,
    EventType.CREDIT_RATING: 7,
}


def _event_type_rank(event_type: EventType) -> int:
    return _EVENT_TYPE_RANK.get(event_type, 99)


def _is_newer_candidate(candidate: CompanyEvent, incumbent: CompanyEvent) -> bool:
    if _event_type_rank(candidate.event_type) < _event_type_rank(incumbent.event_type):
        return True
    if _event_type_rank(candidate.event_type) > _event_type_rank(incumbent.event_type):
        return False
    return (candidate.event_date, candidate.event_id) > (incumbent.event_date, incumbent.event_id)


def pick_canonical_per_period(events: list[CompanyEvent]) -> list[CompanyEvent]:
    """Collapse to one representative event per `period_id`.

    Prefers `QUARTERLY_RESULT`, then annual report, presentation, concall, and
    other filing types. Events without a period are kept and sorted after
    period-keyed rows.
    """
    by_period: dict[int, CompanyEvent] = {}
    no_period: list[CompanyEvent] = []

    for event in events:
        if event.period_id is None:
            no_period.append(event)
            continue
        incumbent = by_period.get(event.period_id)
        if incumbent is None or _is_newer_candidate(event, incumbent):
            by_period[event.period_id] = event

    canonical = list(by_period.values()) + no_period
    canonical.sort(key=lambda e: (e.event_date, e.event_id), reverse=True)
    return canonical
