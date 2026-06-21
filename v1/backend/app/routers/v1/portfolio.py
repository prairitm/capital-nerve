"""POST /v1/portfolio/monitor — the enterprise portfolio monitoring wedge."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models.user import AppUser
from app.schemas.v1.portfolio import PortfolioMonitorRequest, PortfolioMonitorResponse
from app.services.portfolio_monitor import monitor_portfolio

router = APIRouter(prefix="/v1", tags=["v1: portfolio"])


@router.post("/portfolio/monitor", response_model=PortfolioMonitorResponse)
def post_portfolio_monitor(
    payload: PortfolioMonitorRequest,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> PortfolioMonitorResponse:
    return monitor_portfolio(db, payload)
