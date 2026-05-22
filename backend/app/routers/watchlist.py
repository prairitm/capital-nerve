from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.db.enums import SignalDirection
from app.models.intelligence import IntelligenceCard
from app.models.master import Company, Sector
from app.models.user import AppUser, Watchlist, WatchlistCompany
from app.routers._helpers import company_brief

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


class AddCompanyRequest(BaseModel):
    company_id: int


def _ensure_default(db: Session, user: AppUser) -> Watchlist:
    wl = db.scalar(select(Watchlist).where(Watchlist.user_id == user.user_id).limit(1))
    if wl:
        return wl
    wl = Watchlist(user_id=user.user_id, watchlist_name="Default Watchlist")
    db.add(wl)
    db.commit()
    db.refresh(wl)
    return wl


@router.get("")
def my_watchlist(
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> dict[str, Any]:
    wl = _ensure_default(db, user)
    rows = db.execute(
        select(WatchlistCompany, Company, Sector)
        .join(Company, Company.company_id == WatchlistCompany.company_id)
        .join(Sector, Sector.sector_id == Company.sector_id, isouter=True)
        .where(WatchlistCompany.watchlist_id == wl.watchlist_id)
        .order_by(WatchlistCompany.added_at.desc())
    ).all()

    company_payloads: list[dict[str, Any]] = []
    new_events = 0
    negative = 0
    positive = 0
    red_flags = 0
    for _wc, company, sector in rows:
        latest_card = db.scalars(
            select(IntelligenceCard)
            .where(IntelligenceCard.company_id == company.company_id)
            .where(IntelligenceCard.is_published.is_(True))
            .order_by(IntelligenceCard.card_priority.desc(), IntelligenceCard.created_at.desc())
            .limit(1)
        ).first()
        if latest_card:
            new_events += 1
            if latest_card.signal_direction == SignalDirection.NEGATIVE:
                negative += 1
            elif latest_card.signal_direction == SignalDirection.POSITIVE:
                positive += 1
            if latest_card.card_type == "red_flag":
                red_flags += 1
        company_payloads.append(
            {
                "company": company_brief(company, sector).model_dump(),
                "latest_signal": latest_card.signal_direction.value if latest_card and latest_card.signal_direction else None,
                "latest_card_type": latest_card.card_type if latest_card else None,
                "latest_card_headline": latest_card.headline if latest_card else None,
                "watch_next": latest_card.watch_next if latest_card else None,
                "severity": latest_card.severity.value if latest_card and latest_card.severity else None,
            }
        )

    return {
        "watchlist_id": wl.watchlist_id,
        "name": wl.watchlist_name,
        "summary": {
            "tracked": len(company_payloads),
            "new_events": new_events,
            "negative_signals": negative,
            "positive_signals": positive,
            "red_flags": red_flags,
        },
        "companies": company_payloads,
    }


@router.post("/companies")
def add_company(
    body: AddCompanyRequest,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> dict[str, Any]:
    company = db.get(Company, body.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    wl = _ensure_default(db, user)
    exists = db.scalar(
        select(WatchlistCompany).where(
            WatchlistCompany.watchlist_id == wl.watchlist_id,
            WatchlistCompany.company_id == body.company_id,
        )
    )
    if exists:
        return {"added": False, "watchlist_company_id": exists.watchlist_company_id}
    wc = WatchlistCompany(watchlist_id=wl.watchlist_id, company_id=body.company_id)
    db.add(wc)
    db.commit()
    db.refresh(wc)
    return {"added": True, "watchlist_company_id": wc.watchlist_company_id}


@router.delete("/companies/{company_id}")
def remove_company(
    company_id: int,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> dict[str, Any]:
    wl = _ensure_default(db, user)
    wc = db.scalar(
        select(WatchlistCompany).where(
            WatchlistCompany.watchlist_id == wl.watchlist_id,
            WatchlistCompany.company_id == company_id,
        )
    )
    if not wc:
        return {"removed": False}
    db.delete(wc)
    db.commit()
    return {"removed": True}
