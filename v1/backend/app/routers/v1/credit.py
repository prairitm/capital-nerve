"""GET /v1/companies/{symbol}/credit-risk-signals — credit monitoring wedge."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models.user import AppUser
from app.routers._helpers import find_company
from app.schemas.v1.credit import CreditRiskResponse
from app.services.credit_risk import build_credit_risk_response

router = APIRouter(prefix="/v1", tags=["v1: credit"])


@router.get(
    "/companies/{symbol}/credit-risk-signals",
    response_model=CreditRiskResponse,
)
def credit_risk(
    symbol: str,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> CreditRiskResponse:
    company = find_company(db, symbol)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return build_credit_risk_response(db, company)
