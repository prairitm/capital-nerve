"""Admin router — sector list and in-memory company management."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from .. import ids, mapper
from ..builder import Catalog
from ..deps import catalog_dep, get_current_user
from ..schemas import CreateCompanyRequest
from ..state import User, store

router = APIRouter(prefix="/admin", tags=["admin"])

_SECTORS = [
    {"sector_id": 1, "sector_name": "Financials", "industry": "Banking"},
    {"sector_id": 2, "sector_name": "Information Technology", "industry": "IT Services"},
    {"sector_id": 3, "sector_name": "Diversified", "industry": "Conglomerate"},
]


@router.get("/sectors")
def list_sectors(user: User = Depends(get_current_user)) -> list[dict]:
    return _SECTORS


@router.post("/companies", status_code=status.HTTP_201_CREATED)
def create_company(
    body: CreateCompanyRequest,
    user: User = Depends(get_current_user),
) -> dict:
    symbol = body.nse_symbol or body.company_name.upper().replace(" ", "")
    company = {
        "company_id": ids.stable_int("extra-company", symbol),
        "company_name": body.company_name,
        "short_name": symbol,
        "nse_symbol": symbol,
        "bse_code": body.bse_code,
        "sector_name": next((s["sector_name"] for s in _SECTORS if s["sector_id"] == body.sector_id), None),
        "industry": body.industry,
        "market_cap_cr": None,
        "last_price": None,
    }
    store.extra_companies.append(company)
    return {"company": company}


@router.post("/clear-all-companies")
def clear_all_companies(user: User = Depends(get_current_user)) -> dict:
    removed = [c["nse_symbol"] for c in store.extra_companies]
    store.extra_companies.clear()
    return {"companies_removed": len(removed), "symbols": removed}
