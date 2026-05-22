from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models.events import CompanyEvent
from app.models.intelligence import IntelligenceCard
from app.models.master import Company, Sector
from app.models.user import AppUser
from app.routers._helpers import company_brief

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
def search(
    q: str = Query(min_length=1),
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> dict[str, Any]:
    like = f"%{q.lower()}%"

    companies = db.execute(
        select(Company, Sector)
        .join(Sector, Sector.sector_id == Company.sector_id, isouter=True)
        .where(
            or_(
                Company.company_name.ilike(like),
                Company.nse_symbol.ilike(like),
                Company.bse_code.ilike(like),
                Company.short_name.ilike(like),
            )
        )
        .limit(10)
    ).all()

    events = db.execute(
        select(CompanyEvent, Company)
        .join(Company, Company.company_id == CompanyEvent.company_id)
        .where(
            or_(
                CompanyEvent.event_title.ilike(like),
                CompanyEvent.summary_text.ilike(like),
            )
        )
        .order_by(CompanyEvent.event_date.desc())
        .limit(10)
    ).all()

    cards = db.execute(
        select(IntelligenceCard, Company)
        .join(Company, Company.company_id == IntelligenceCard.company_id)
        .where(
            or_(
                IntelligenceCard.headline.ilike(like),
                IntelligenceCard.one_line_summary.ilike(like),
                IntelligenceCard.detailed_explanation.ilike(like),
            )
        )
        .order_by(IntelligenceCard.card_priority.desc())
        .limit(15)
    ).all()

    return {
        "companies": [company_brief(c, s).model_dump() for (c, s) in companies],
        "events": [
            {
                "event_id": e.event_id,
                "event_type": e.event_type.value,
                "event_title": e.event_title,
                "event_date": e.event_date.isoformat(),
                "company_name": c.company_name,
                "company_symbol": c.nse_symbol or c.bse_code,
            }
            for (e, c) in events
        ],
        "cards": [
            {
                "card_id": ic.card_id,
                "card_type": ic.card_type,
                "headline": ic.headline,
                "one_line_summary": ic.one_line_summary,
                "signal_direction": ic.signal_direction.value if ic.signal_direction else None,
                "severity": ic.severity.value if ic.severity else None,
                "company_name": c.company_name,
                "company_symbol": c.nse_symbol or c.bse_code,
            }
            for (ic, c) in cards
        ],
    }
