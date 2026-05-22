"""GET /v1/companies/{symbol}/result-brief — sell-side analyst briefing wedge."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models.user import AppUser
from app.routers._helpers import find_company
from app.schemas.v1.result_brief import ResultBrief
from app.services.result_brief_builder import build_result_brief

router = APIRouter(prefix="/v1", tags=["v1: result-brief"])


@router.get(
    "/companies/{symbol}/result-brief",
    response_model=ResultBrief,
)
def result_brief(
    symbol: str,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
    period: str | None = Query(default=None, description="Period display label e.g. Q4FY26"),
) -> ResultBrief:
    company = find_company(db, symbol)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    brief = build_result_brief(db, company, period)
    if not brief:
        raise HTTPException(status_code=404, detail="No quarterly result for that period")
    return brief
