"""Market-data ingest endpoint.

`POST /v1/market-data/{company_id}` writes one or more `MarketDataPoint`
rows and projects the latest snapshot down into `FinancialStatementFact`
records keyed by the new normalized codes (`share_price_close`, `volume`,
`avg_volume_20d`, `delivery_pct`, `market_cap`, `pre_event_close`,
`post_event_close`). The metric engine then picks them up exactly like
financial line items — no special-case code path for valuation metrics.
"""
from __future__ import annotations

from datetime import date as Date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_admin, get_db
from app.db.enums import AuditStatus, ConsolidationType
from app.models.facts import FinancialLineItemDefinition, FinancialStatementFact
from app.models.market import MarketDataPoint
from app.models.master import Company, FinancialPeriod
from app.models.user import AppUser

router = APIRouter(prefix="/v1/market-data", tags=["market-data"])


class MarketDataPointIn(BaseModel):
    trade_date: Date
    open_price: float | None = None
    high_price: float | None = None
    low_price: float | None = None
    close_price: float | None = None
    volume: float | None = None
    delivery_qty: float | None = None
    delivery_pct: float | None = None
    avg_volume_20d: float | None = None
    market_cap: float | None = None
    fifty_two_week_high: float | None = None
    fifty_two_week_low: float | None = None
    pre_event_close: float | None = None
    post_event_close: float | None = None


class MarketDataIngestRequest(BaseModel):
    points: list[MarketDataPointIn] = Field(min_length=1)
    period_id: int | None = None


@router.post("/{company_id}", status_code=status.HTTP_202_ACCEPTED)
def ingest_market_data(
    company_id: int,
    body: MarketDataIngestRequest,
    db: Session = Depends(get_db),
    admin: AppUser = Depends(get_current_admin),
) -> dict:
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    period = db.get(FinancialPeriod, body.period_id) if body.period_id else None
    if body.period_id and period is None:
        raise HTTPException(status_code=404, detail="Period not found")

    written = 0
    latest: MarketDataPointIn | None = None
    for raw in body.points:
        existing = db.scalar(
            select(MarketDataPoint).where(
                MarketDataPoint.company_id == company_id,
                MarketDataPoint.trade_date == raw.trade_date,
            )
        )
        if existing:
            for field, value in raw.model_dump(exclude={"pre_event_close", "post_event_close"}).items():
                if value is not None:
                    setattr(existing, field, value)
        else:
            point = MarketDataPoint(
                company_id=company_id,
                trade_date=raw.trade_date,
                open_price=raw.open_price,
                high_price=raw.high_price,
                low_price=raw.low_price,
                close_price=raw.close_price,
                volume=raw.volume,
                delivery_qty=raw.delivery_qty,
                delivery_pct=raw.delivery_pct,
                avg_volume_20d=raw.avg_volume_20d,
                market_cap=raw.market_cap,
                fifty_two_week_high=raw.fifty_two_week_high,
                fifty_two_week_low=raw.fifty_two_week_low,
            )
            db.add(point)
        written += 1
        if latest is None or raw.trade_date >= latest.trade_date:
            latest = raw
    db.flush()

    facts_written = 0
    if latest is not None and period is not None:
        facts_written = _project_to_facts(
            db,
            company_id=company_id,
            period=period,
            point=latest,
        )

    db.commit()
    return {
        "company_id": company_id,
        "points_written": written,
        "facts_written": facts_written,
        "period_id": period.period_id if period else None,
    }


_LINE_ITEM_BY_FIELD: dict[str, str] = {
    "close_price": "share_price_close",
    "volume": "volume",
    "delivery_pct": "delivery_pct",
    "avg_volume_20d": "avg_volume_20d",
    "market_cap": "market_cap",
    "pre_event_close": "pre_event_close",
    "post_event_close": "post_event_close",
}


def _project_to_facts(
    db: Session,
    *,
    company_id: int,
    period: FinancialPeriod,
    point: MarketDataPointIn,
) -> int:
    """Write a `FinancialStatementFact` row for every populated market field.

    The engine reads facts (not market_data_points) so that valuation /
    market-reaction metrics share one code path with the rest of the
    pipeline. Re-ingesting the same period overwrites the prior snapshot
    via the unique constraint on `financial_statement_facts`.
    """
    written = 0
    for field, code in _LINE_ITEM_BY_FIELD.items():
        value = getattr(point, field, None)
        if value is None:
            continue
        li_def_id = db.scalar(
            select(FinancialLineItemDefinition.line_item_def_id).where(
                FinancialLineItemDefinition.normalized_code == code
            )
        )
        if li_def_id is None:
            continue
        existing = db.scalar(
            select(FinancialStatementFact).where(
                FinancialStatementFact.company_id == company_id,
                FinancialStatementFact.period_id == period.period_id,
                FinancialStatementFact.line_item_def_id == li_def_id,
                FinancialStatementFact.consolidation == ConsolidationType.STANDALONE,
                FinancialStatementFact.period_value_type == "CURRENT",
            )
        )
        if existing:
            existing.value = float(value)
            written += 1
            continue
        db.add(
            FinancialStatementFact(
                company_id=company_id,
                period_id=period.period_id,
                line_item_def_id=li_def_id,
                consolidation=ConsolidationType.STANDALONE,
                audit_status=AuditStatus.UNAUDITED,
                value=float(value),
                unit="market",
                period_value_type="CURRENT",
                confidence_score=95.0,
            )
        )
        written += 1
    return written
