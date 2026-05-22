"""Admin-only maintenance endpoints (company onboarding, bulk purge)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_admin, get_db
from app.db.enums import CompanyStatus, ExchangeCode
from app.models.events import CompanyEvent, DocumentPage, ExtractionJob, SourceDocument
from app.models.facts import (
    AnalystQuestion,
    AnnouncementFact,
    CompanySegment,
    ConcallFact,
    ConcallSpeaker,
    ExtractedValue,
    FinancialStatementFact,
    PresentationFact,
    SegmentFact,
    TranscriptChunk,
)
from app.models.intelligence import (
    CalculatedMetric,
    CardEvidence,
    GeneratedSignal,
    IntelligenceCard,
)
from app.models.master import Company, Sector, Security
from app.models.review import ReviewQueue
from app.models.user import Alert, AppUser, UserWatchItem, WatchlistCompany
from app.routers._helpers import company_brief

router = APIRouter(prefix="/admin", tags=["admin"])


class CreateCompanyRequest(BaseModel):
    company_name: str = Field(min_length=1, max_length=256)
    short_name: str | None = None
    nse_symbol: str | None = Field(default=None, max_length=32)
    bse_code: str | None = None
    isin: str | None = None
    sector_name: str | None = None
    industry: str | None = None


class SectorBrief(BaseModel):
    sector_id: int
    sector_name: str
    industry: str | None


@router.get("/sectors", response_model=list[SectorBrief])
def list_sectors(
    db: Session = Depends(get_db),
    admin: AppUser = Depends(get_current_admin),
) -> list[SectorBrief]:
    rows = db.scalars(select(Sector).order_by(Sector.sector_name.asc())).all()
    return [
        SectorBrief(sector_id=s.sector_id, sector_name=s.sector_name, industry=s.industry)
        for s in rows
    ]


@router.post("/companies", status_code=status.HTTP_201_CREATED)
def create_company(
    body: CreateCompanyRequest,
    db: Session = Depends(get_db),
    admin: AppUser = Depends(get_current_admin),
) -> dict:
    """Register a new issuer before uploading its first filing."""
    if body.nse_symbol:
        clash = db.scalar(select(Company).where(Company.nse_symbol == body.nse_symbol.upper()))
        if clash:
            raise HTTPException(
                status_code=400,
                detail=f"NSE symbol {body.nse_symbol.upper()} already registered",
            )

    sector: Sector | None = None
    if body.sector_name:
        sector = db.scalar(select(Sector).where(Sector.sector_name == body.sector_name))
        if not sector:
            sector = Sector(
                sector_name=body.sector_name.strip(),
                industry=body.industry,
            )
            db.add(sector)
            db.flush()

    company = Company(
        company_name=body.company_name.strip(),
        short_name=(body.short_name or body.company_name).strip(),
        nse_symbol=body.nse_symbol.upper() if body.nse_symbol else None,
        bse_code=body.bse_code,
        isin=body.isin,
        sector_id=sector.sector_id if sector else None,
        industry=body.industry,
        status=CompanyStatus.ACTIVE,
    )
    db.add(company)
    db.flush()

    if company.nse_symbol:
        db.add(
            Security(
                company_id=company.company_id,
                exchange=ExchangeCode.NSE,
                symbol=company.nse_symbol,
                isin=company.isin,
                security_name=company.company_name,
                is_active=True,
            )
        )

    db.commit()
    db.refresh(company)
    sector_row = db.get(Sector, company.sector_id) if company.sector_id else None
    brief = company_brief(company, sector_row)
    return {"company": brief.model_dump()}


def _purge_company_rows(db: Session, company_ids: list[int]) -> None:
    """Delete every row that references the given companies in dependency order."""
    if not company_ids:
        return

    doc_ids = list(
        db.scalars(
            select(SourceDocument.document_id).where(SourceDocument.company_id.in_(company_ids))
        ).all()
    )
    card_ids = list(
        db.scalars(
            select(IntelligenceCard.card_id).where(IntelligenceCard.company_id.in_(company_ids))
        ).all()
    )

    db.execute(delete(UserWatchItem).where(UserWatchItem.company_id.in_(company_ids)))
    db.execute(delete(Alert).where(Alert.company_id.in_(company_ids)))
    db.execute(delete(ReviewQueue).where(ReviewQueue.company_id.in_(company_ids)))
    db.execute(delete(WatchlistCompany).where(WatchlistCompany.company_id.in_(company_ids)))

    if card_ids:
        db.execute(delete(CardEvidence).where(CardEvidence.card_id.in_(card_ids)))
        db.execute(delete(IntelligenceCard).where(IntelligenceCard.card_id.in_(card_ids)))

    for model in (
        GeneratedSignal,
        CalculatedMetric,
        AnalystQuestion,
        ConcallFact,
        ConcallSpeaker,
        PresentationFact,
        AnnouncementFact,
        TranscriptChunk,
        SegmentFact,
        CompanySegment,
        FinancialStatementFact,
        ExtractedValue,
    ):
        db.execute(delete(model).where(model.company_id.in_(company_ids)))

    db.execute(delete(ExtractionJob).where(ExtractionJob.company_id.in_(company_ids)))
    if doc_ids:
        db.execute(delete(DocumentPage).where(DocumentPage.document_id.in_(doc_ids)))
    for model in (SourceDocument, CompanyEvent, Security):
        db.execute(delete(model).where(model.company_id.in_(company_ids)))


@router.post("/clear-all-companies")
def clear_all_companies(
    db: Session = Depends(get_db),
    admin: AppUser = Depends(get_current_admin),
) -> dict:
    """Delete every company and all dependent intelligence rows.

    Keeps sectors, financial periods, line-item / metric / signal
    definitions, and users — i.e. everything that ``seed_catalog`` writes.
    """
    rows = db.execute(
        select(Company.company_id, Company.nse_symbol, Company.bse_code).order_by(Company.company_id)
    ).all()
    if not rows:
        return {"companies_removed": 0, "symbols": []}

    company_ids = [r.company_id for r in rows]
    symbols = [r.nse_symbol or r.bse_code for r in rows if r.nse_symbol or r.bse_code]

    _purge_company_rows(db, company_ids)
    removed = db.execute(delete(Company).where(Company.company_id.in_(company_ids))).rowcount
    db.commit()
    return {
        "companies_removed": removed or len(company_ids),
        "symbols": symbols,
    }
