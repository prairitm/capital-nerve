"""GET /v1/companies/{symbol}/retail-summary — consumer brokerage wedge."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models.user import AppUser
from app.routers._helpers import find_company
from app.schemas.v1.retail import RetailSummary
from app.services.retail_summary import build_retail_summary

router = APIRouter(prefix="/v1", tags=["v1: retail"])


@router.get(
    "/companies/{symbol}/retail-summary",
    response_model=RetailSummary,
)
def retail_summary(
    symbol: str,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> RetailSummary:
    company = find_company(db, symbol)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return build_retail_summary(db, company)
