from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models.master import Company
from app.models.user import Alert, AppUser

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("")
def list_alerts(
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
    unread: bool = False,
) -> list[dict[str, Any]]:
    stmt = select(Alert, Company).join(Company, Company.company_id == Alert.company_id, isouter=True).where(Alert.user_id == user.user_id)
    if unread:
        stmt = stmt.where(Alert.is_read.is_(False))
    stmt = stmt.order_by(Alert.created_at.desc()).limit(50)
    rows = db.execute(stmt).all()
    return [
        {
            "alert_id": a.alert_id,
            "alert_title": a.alert_title,
            "alert_message": a.alert_message,
            "severity": a.severity.value if a.severity else None,
            "is_read": a.is_read,
            "created_at": a.created_at.isoformat(),
            "company_name": c.company_name if c else None,
            "company_symbol": (c.nse_symbol or c.bse_code) if c else None,
            "event_id": a.event_id,
            "card_id": a.card_id,
        }
        for (a, c) in rows
    ]


@router.patch("/{alert_id}/read")
def mark_read(
    alert_id: int,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> dict[str, Any]:
    alert = db.get(Alert, alert_id)
    if not alert or alert.user_id != user.user_id:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.is_read = True
    db.commit()
    return {"alert_id": alert.alert_id, "is_read": True}
