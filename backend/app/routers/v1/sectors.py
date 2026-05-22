"""GET /v1/sectors/{sector_name}/signals — cross-company sector signal roll-up."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.db.enums import SeverityLevel, SignalDirection
from app.models.intelligence import GeneratedSignal, SignalDefinition
from app.models.master import Company, FinancialPeriod, Sector
from app.models.user import AppUser
from app.routers._helpers import company_brief, period_brief
from app.schemas.v1.sector import SectorSignalRow, SectorSignalsResponse

router = APIRouter(prefix="/v1", tags=["v1: sectors"])


@router.get("/sectors/{sector_name}/signals", response_model=SectorSignalsResponse)
def sector_signals(
    sector_name: str,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
    direction: SignalDirection | None = None,
    severity: SeverityLevel | None = None,
    period: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> SectorSignalsResponse:
    sector = db.scalar(select(Sector).where(Sector.sector_name.ilike(sector_name)))
    if not sector:
        # Fallback to partial match so URLs like "Information%20Technology" still
        # match the seeded sector "IT Services".
        sector = db.scalar(select(Sector).where(Sector.sector_name.ilike(f"%{sector_name}%")))
    if not sector:
        raise HTTPException(status_code=404, detail="Sector not found")

    company_count = (
        db.scalar(select(func.count(Company.company_id)).where(Company.sector_id == sector.sector_id))
        or 0
    )

    stmt = (
        select(GeneratedSignal, SignalDefinition, Company, FinancialPeriod)
        .join(SignalDefinition, SignalDefinition.signal_def_id == GeneratedSignal.signal_def_id)
        .join(Company, Company.company_id == GeneratedSignal.company_id)
        .outerjoin(FinancialPeriod, FinancialPeriod.period_id == GeneratedSignal.period_id)
        .where(Company.sector_id == sector.sector_id)
        .where(GeneratedSignal.is_published.is_(True))
    )
    if direction:
        stmt = stmt.where(GeneratedSignal.signal_direction == direction)
    if severity:
        stmt = stmt.where(GeneratedSignal.severity == severity)
    if period:
        clean = period.strip()
        stmt = stmt.where(
            (FinancialPeriod.display_label.ilike(clean)) | (FinancialPeriod.fy_label.ilike(clean))
        )
    stmt = stmt.order_by(
        GeneratedSignal.signal_score.desc().nullslast(), GeneratedSignal.created_at.desc()
    ).limit(limit)

    rows = db.execute(stmt).all()
    signals = [
        SectorSignalRow(
            signal_id=sig.signal_id,
            signal_code=sd.signal_code,
            signal_name=sd.signal_name,
            signal_category=sd.signal_category,
            direction=sig.signal_direction,
            severity=sig.severity,
            confidence_score=float(sig.confidence_score) if sig.confidence_score is not None else None,
            signal_score=float(sig.signal_score) if sig.signal_score is not None else None,
            headline=sig.headline,
            company=company_brief(comp, sector),
            period=period_brief(per),
            event_id=sig.event_id,
        )
        for (sig, sd, comp, per) in rows
    ]

    return SectorSignalsResponse(
        sector_name=sector.sector_name,
        company_count=company_count,
        signal_count=len(signals),
        signals=signals,
    )
