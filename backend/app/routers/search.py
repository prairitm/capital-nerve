from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.db.enums import DocumentType
from app.models.events import CompanyEvent
from app.models.intelligence import IntelligenceCard
from app.models.master import Company, Sector
from app.models.user import AppUser
from app.routers._helpers import company_brief
from app.services.data_ask import DataAskError
from app.services.document_search import search_pages_fts
from app.services.unified_ask import UnifiedAskResult, ask_unified

router = APIRouter(prefix="/search", tags=["search"])


class DocumentSearchHitOut(BaseModel):
    document_id: int
    page_number: int
    snippet: str
    document_type: DocumentType
    document_title: str
    company_id: int
    company_name: str
    company_symbol: str | None
    rank: float


class AskRequest(BaseModel):
    q: str = Field(min_length=1)
    company_id: int | None = None
    event_id: int | None = None


class AskCitationOut(BaseModel):
    page_id: int
    document_id: int
    page_number: int
    quote: str


class AskResponse(BaseModel):
    answer: str
    mode: Literal["sql", "rag"]
    citations: list[AskCitationOut] = []
    retrieval_mode: Literal["hybrid", "fts_only"] | None = None
    sql: str | None = None
    columns: list[str] = []
    rows: list[dict[str, Any]] = []
    row_count: int = 0


class DataAskRequest(BaseModel):
    q: str = Field(min_length=1)


class DataAskResponse(BaseModel):
    answer: str
    sql: str
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int


def _document_type_param(value: str | None) -> DocumentType | None:
    if not value:
        return None
    return DocumentType(value)


@router.get("")
def search(
    q: str = Query(min_length=1),
    company_id: int | None = None,
    document_type: str | None = None,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> dict[str, Any]:
    like = f"%{q.lower()}%"
    doc_type = _document_type_param(document_type)

    companies = db.execute(
        select(Company, Sector)
        .join(Sector, Sector.sector_id == Company.sector_id, isouter=True)
        .where(
            or_(
                Company.company_name.ilike(like),
                Company.nse_symbol.ilike(like),
                Company.bse_code.ilike(like),
                Company.short_name.ilike(like),
            )
        )
        .limit(10)
    ).all()

    events = db.execute(
        select(CompanyEvent, Company)
        .join(Company, Company.company_id == CompanyEvent.company_id)
        .where(
            or_(
                CompanyEvent.event_title.ilike(like),
                CompanyEvent.summary_text.ilike(like),
            )
        )
        .order_by(CompanyEvent.event_date.desc())
        .limit(10)
    ).all()

    cards = db.execute(
        select(IntelligenceCard, Company)
        .join(Company, Company.company_id == IntelligenceCard.company_id)
        .where(
            or_(
                IntelligenceCard.headline.ilike(like),
                IntelligenceCard.one_line_summary.ilike(like),
                IntelligenceCard.detailed_explanation.ilike(like),
            )
        )
        .order_by(IntelligenceCard.card_priority.desc())
        .limit(15)
    ).all()

    document_hits = search_pages_fts(
        db,
        q,
        company_id=company_id,
        document_type=doc_type,
        limit=15,
    )

    return {
        "companies": [company_brief(c, s).model_dump() for (c, s) in companies],
        "events": [
            {
                "event_id": e.event_id,
                "event_type": e.event_type.value,
                "event_title": e.event_title,
                "event_date": e.event_date.isoformat(),
                "company_name": c.company_name,
                "company_symbol": c.nse_symbol or c.bse_code,
            }
            for (e, c) in events
        ],
        "cards": [
            {
                "card_id": ic.card_id,
                "card_type": ic.card_type,
                "headline": ic.headline,
                "one_line_summary": ic.one_line_summary,
                "signal_direction": ic.signal_direction.value if ic.signal_direction else None,
                "severity": ic.severity.value if ic.severity else None,
                "company_name": c.company_name,
                "company_symbol": c.nse_symbol or c.bse_code,
            }
            for (ic, c) in cards
        ],
        "document_hits": [
            DocumentSearchHitOut(
                document_id=hit.document_id,
                page_number=hit.page_number,
                snippet=hit.snippet,
                document_type=hit.document_type,
                document_title=hit.document_title,
                company_id=hit.company_id,
                company_name=hit.company_name,
                company_symbol=hit.company_symbol,
                rank=hit.rank,
            ).model_dump()
            for hit in document_hits
        ],
    }


def _to_ask_response(result: UnifiedAskResult) -> AskResponse:
    return AskResponse(
        answer=result.answer,
        mode=result.mode,
        citations=[
            AskCitationOut(
                page_id=c.page_id,
                document_id=c.document_id,
                page_number=c.page_number,
                quote=c.quote,
            )
            for c in result.citations
        ],
        retrieval_mode=result.retrieval_mode,  # type: ignore[arg-type]
        sql=result.sql,
        columns=result.columns,
        rows=result.rows,
        row_count=result.row_count,
    )


@router.post("/ask", response_model=AskResponse)
def search_ask(
    body: AskRequest,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> AskResponse:
    try:
        result = ask_unified(
            db,
            body.q,
            company_id=body.company_id,
            event_id=body.event_id,
        )
    except DataAskError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_ask_response(result)


@router.post("/ask-data", response_model=DataAskResponse)
def search_ask_data(
    body: DataAskRequest,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> DataAskResponse:
    """Legacy alias — same unified ask, but requires a SQL (facts) answer."""
    try:
        result = ask_unified(db, body.q)
    except DataAskError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result.mode != "sql":
        raise HTTPException(
            status_code=400,
            detail="This question is better answered from filings. Use POST /search/ask instead.",
        )
    return DataAskResponse(
        answer=result.answer,
        sql=result.sql or "",
        columns=result.columns,
        rows=result.rows,
        row_count=result.row_count,
    )
