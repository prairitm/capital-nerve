"""Turn a CLI period range into a deterministic list of `PeriodSpec`.

The bulk ingestor accepts three input styles:

- ``--from "Q1 FY25-26" --to "Q3 FY25-26"`` (quarter range).
- ``--start 2024-04-01 --end 2026-03-31`` (date range).
- ``--last-quarters 6`` (rolling window ending at the current quarter).

`expand_range` validates exactly one of these is supplied and returns the
list in chronological order. `--include-annual` opt-in adds an extra
ANNUAL `PeriodSpec` for every FY whose Q4 falls inside the resulting set.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional

from app.db.enums import PeriodType
from app.services.ingest_common import (
    format_annual_display_label,
    format_fy_label,
    parse_period_label,
    quarter_date_bounds,
)
from app.services.ir_discovery.schemas import PeriodSpec


@dataclass(frozen=True)
class _QuarterKey:
    fy_year: int
    quarter: int

    def to_int(self) -> int:
        return self.fy_year * 10 + self.quarter


class PeriodRangeError(ValueError):
    """Raised when CLI inputs cannot be turned into a coherent period list."""


def expand_range(
    *,
    period_from: str | None = None,
    period_to: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    last_quarters: int | None = None,
    today: date | None = None,
    include_annual: bool = False,
) -> list[PeriodSpec]:
    """Materialise the chosen CLI input into a chronological list of periods.

    Exactly one of the three input groups must be supplied:

    - ``period_from`` + ``period_to`` (both required together).
    - ``start_date`` + ``end_date`` (both required together).
    - ``last_quarters`` (positive integer).

    When ``include_annual`` is true, each FY whose Q4 lies in the produced
    window also gets an `ANNUAL` `PeriodSpec` appended after that Q4.
    """
    modes_supplied = sum(
        [
            bool(period_from or period_to),
            bool(start_date or end_date),
            last_quarters is not None,
        ]
    )
    if modes_supplied == 0:
        raise PeriodRangeError(
            "Provide one of --from/--to, --start/--end, or --last-quarters."
        )
    if modes_supplied > 1:
        raise PeriodRangeError(
            "Provide only one of --from/--to, --start/--end, or --last-quarters."
        )

    if period_from or period_to:
        if not (period_from and period_to):
            raise PeriodRangeError(
                "Both --from and --to are required when using a quarter range."
            )
        quarters = _quarters_between_labels(period_from, period_to)
    elif start_date or end_date:
        if not (start_date and end_date):
            raise PeriodRangeError(
                "Both --start and --end are required when using a date range."
            )
        if end_date < start_date:
            raise PeriodRangeError("--end must be on or after --start.")
        quarters = _quarters_between_dates(start_date, end_date)
    else:
        if last_quarters is None or last_quarters <= 0:
            raise PeriodRangeError("--last-quarters must be a positive integer.")
        anchor = today or date.today()
        quarters = _last_n_quarters(anchor, last_quarters)

    specs = [_quarter_spec(q.fy_year, q.quarter) for q in quarters]
    if include_annual:
        specs = _interleave_annuals(specs)
    return specs


# ---------------------------------------------------------------------------
# Quarter math
# ---------------------------------------------------------------------------


def _quarters_between_labels(label_from: str, label_to: str) -> list[_QuarterKey]:
    parsed_from = parse_period_label(label_from)
    parsed_to = parse_period_label(label_to)
    if not parsed_from:
        raise PeriodRangeError(
            f"Could not parse --from {label_from!r}; expected 'Q[1-4] FY25-26'."
        )
    if not parsed_to:
        raise PeriodRangeError(
            f"Could not parse --to {label_to!r}; expected 'Q[1-4] FY25-26'."
        )
    qf = _QuarterKey(fy_year=parsed_from[1], quarter=parsed_from[0])
    qt = _QuarterKey(fy_year=parsed_to[1], quarter=parsed_to[0])
    if qt.to_int() < qf.to_int():
        raise PeriodRangeError("--to must be on or after --from.")
    return list(_iter_quarter_keys(qf, qt))


def _quarters_between_dates(start: date, end: date) -> list[_QuarterKey]:
    """Every FY quarter whose window intersects ``[start, end]``."""
    out: list[_QuarterKey] = []
    cursor = _quarter_key_for_date(start)
    end_key = _quarter_key_for_date(end)
    for key in _iter_quarter_keys(cursor, end_key):
        out.append(key)
    return out


def _last_n_quarters(today: date, n: int) -> list[_QuarterKey]:
    """The most recent ``n`` quarters ending at ``today``'s quarter."""
    end_key = _quarter_key_for_date(today)
    keys = _walk_quarters_back(end_key, n)
    return list(reversed(keys))


def _quarter_key_for_date(d: date) -> _QuarterKey:
    """Indian-FY quarter key containing ``d``."""
    month = d.month
    quarter = ((month - 4) % 12) // 3 + 1
    fy_year = d.year if month >= 4 else d.year - 1
    return _QuarterKey(fy_year=fy_year, quarter=quarter)


def _iter_quarter_keys(
    start: _QuarterKey, end: _QuarterKey
) -> Iterable[_QuarterKey]:
    cur = start
    while cur.to_int() <= end.to_int():
        yield cur
        cur = _next_quarter_key(cur)


def _next_quarter_key(key: _QuarterKey) -> _QuarterKey:
    if key.quarter < 4:
        return _QuarterKey(fy_year=key.fy_year, quarter=key.quarter + 1)
    return _QuarterKey(fy_year=key.fy_year + 1, quarter=1)


def _previous_quarter_key(key: _QuarterKey) -> _QuarterKey:
    if key.quarter > 1:
        return _QuarterKey(fy_year=key.fy_year, quarter=key.quarter - 1)
    return _QuarterKey(fy_year=key.fy_year - 1, quarter=4)


def _walk_quarters_back(end: _QuarterKey, n: int) -> list[_QuarterKey]:
    keys = [end]
    cur = end
    for _ in range(n - 1):
        cur = _previous_quarter_key(cur)
        keys.append(cur)
    return keys


def _quarter_spec(fy_year: int, quarter: int) -> PeriodSpec:
    start, end, fy_label, display_label = quarter_date_bounds(fy_year, quarter)
    return PeriodSpec(
        fy_year=fy_year,
        period_type=PeriodType.QUARTERLY,
        quarter=quarter,
        period_start=start,
        period_end=end,
        fy_label=fy_label,
        display_label=display_label,
    )


def _annual_spec(fy_year: int) -> PeriodSpec:
    fy_label = format_fy_label(fy_year)
    return PeriodSpec(
        fy_year=fy_year,
        period_type=PeriodType.ANNUAL,
        quarter=None,
        period_start=date(fy_year, 4, 1),
        period_end=date(fy_year + 1, 3, 31),
        fy_label=fy_label,
        display_label=format_annual_display_label(fy_year),
    )


def _interleave_annuals(specs: list[PeriodSpec]) -> list[PeriodSpec]:
    """Append an ANNUAL spec right after every Q4 in ``specs``.

    Ordering: ``[Q1 FY25, Q2 FY25, Q3 FY25, Q4 FY25, FY25, Q1 FY26 ...]``.
    """
    out: list[PeriodSpec] = []
    seen_annual: set[int] = set()
    for s in specs:
        out.append(s)
        if s.is_quarterly and s.quarter == 4 and s.fy_year not in seen_annual:
            out.append(_annual_spec(s.fy_year))
            seen_annual.add(s.fy_year)
    return out


__all__ = [
    "PeriodRangeError",
    "expand_range",
]
