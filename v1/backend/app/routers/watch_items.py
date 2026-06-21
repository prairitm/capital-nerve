from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models.master import Company
from app.models.user import AppUser, UserWatchItem

router = APIRouter(prefix="/watch-items", tags=["watch-items"])


class CreateWatchItem(BaseModel):
    company_id: int
    card_id: int | None = None
    metric_def_id: int | None = None
    title: str
    description: str | None = None
    current_value: float | None = None
    target_value: float | None = None
    condition_operator: str | None = None
    condition_json: dict | None = None


class UpdateWatchItem(BaseModel):
    title: str | None = None
    description: str | None = None
    target_value: float | None = None
    condition_operator: str | None = None
    condition_json: dict | None = None
    is_active: bool | None = None


def _to_payload(w: UserWatchItem, company: Company) -> dict[str, Any]:
    return {
        "watch_item_id": w.watch_item_id,
        "company_id": w.company_id,
        "company_name": company.company_name,
        "company_symbol": company.nse_symbol or company.bse_code,
        "card_id": w.card_id,
        "metric_def_id": w.metric_def_id,
        "title": w.title,
        "description": w.description,
        "current_value": float(w.current_value) if w.current_value is not None else None,
        "target_value": float(w.target_value) if w.target_value is not None else None,
        "condition_operator": w.condition_operator,
        "condition_json": w.condition_json,
        "is_active": w.is_active,
        "created_at": w.created_at.isoformat(),
    }


@router.get("")
def list_items(
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    rows = db.execute(
        select(UserWatchItem, Company)
        .join(Company, Company.company_id == UserWatchItem.company_id)
        .where(UserWatchItem.user_id == user.user_id)
        .order_by(UserWatchItem.created_at.desc())
    ).all()
    return [_to_payload(w, c) for (w, c) in rows]


@router.post("")
def create_item(
    body: CreateWatchItem,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> dict[str, Any]:
    company = db.get(Company, body.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    item = UserWatchItem(
        user_id=user.user_id,
        company_id=body.company_id,
        card_id=body.card_id,
        metric_def_id=body.metric_def_id,
        title=body.title,
        description=body.description,
        current_value=body.current_value,
        target_value=body.target_value,
        condition_operator=body.condition_operator,
        condition_json=body.condition_json or {},
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _to_payload(item, company)


@router.patch("/{watch_item_id}")
def update_item(
    watch_item_id: int,
    body: UpdateWatchItem,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> dict[str, Any]:
    item = db.get(UserWatchItem, watch_item_id)
    if not item or item.user_id != user.user_id:
        raise HTTPException(status_code=404, detail="Watch item not found")
    for key, val in body.model_dump(exclude_none=True).items():
        setattr(item, key, val)
    db.commit()
    db.refresh(item)
    company = db.get(Company, item.company_id)
    return _to_payload(item, company)


@router.delete("/{watch_item_id}")
def delete_item(
    watch_item_id: int,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> dict[str, Any]:
    item = db.get(UserWatchItem, watch_item_id)
    if not item or item.user_id != user.user_id:
        raise HTTPException(status_code=404, detail="Watch item not found")
    db.delete(item)
    db.commit()
    return {"deleted": True}
