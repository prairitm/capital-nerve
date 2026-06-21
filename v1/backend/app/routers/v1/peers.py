"""GET /v1/companies/{symbol}/peer-narrative — IR competitive intelligence wedge."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models.user import AppUser
from app.routers._helpers import find_company
from app.schemas.v1.peer import PeerNarrativeComparison
from app.services.peer_narrative import build_peer_narrative

router = APIRouter(prefix="/v1", tags=["v1: peers"])


@router.get(
    "/companies/{symbol}/peer-narrative",
    response_model=PeerNarrativeComparison,
)
def peer_narrative(
    symbol: str,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> PeerNarrativeComparison:
    company = find_company(db, symbol)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return build_peer_narrative(db, company)
