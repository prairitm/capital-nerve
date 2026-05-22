"""Credit risk signal filter.

Filters `generated_signals` to credit-relevant categories / codes and produces a
bucketed view (debt, coverage, earnings quality, auditor, rating, working
capital). The overall risk level is the highest severity among matching
NEGATIVE / MIXED signals.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import SeverityLevel, SignalDirection
from app.models.intelligence import GeneratedSignal, SignalDefinition
from app.models.master import Company, FinancialPeriod
from app.routers._helpers import company_brief, period_brief
from app.schemas.v1.credit import CreditDimension, CreditRiskResponse, CreditRiskSignal

# Each entry maps a (signal_category, signal_code) → credit dimension. Codes
# take precedence; missing codes fall back to the category mapping below.
_CODE_TO_DIMENSION: dict[str, CreditDimension] = {
    "audit_redflag": "auditor",
    "finance_cost_pressure": "coverage",
    "weak_profit_quality_other_income": "earnings_quality",
    "margin_compression": "earnings_quality",
    "revenue_deceleration": "earnings_quality",
}

_CATEGORY_TO_DIMENSION: dict[str, CreditDimension] = {
    "red_flag": "auditor",
    "expense": "coverage",
    "profit_quality": "earnings_quality",
    "margin": "earnings_quality",
    "balance_sheet": "debt",
    "working_capital": "working_capital",
    "rating": "rating",
}

# Severity → numeric rank for "overall_risk" reduction.
_SEVERITY_RANK: dict[SeverityLevel, int] = {
    SeverityLevel.LOW: 1,
    SeverityLevel.MEDIUM: 2,
    SeverityLevel.HIGH: 3,
    SeverityLevel.CRITICAL: 4,
}
_RANK_TO_SEVERITY: dict[int, SeverityLevel] = {v: k for k, v in _SEVERITY_RANK.items()}


def _dimension_for(sig: GeneratedSignal, sd: SignalDefinition) -> CreditDimension | None:
    if sd.signal_code in _CODE_TO_DIMENSION:
        return _CODE_TO_DIMENSION[sd.signal_code]
    return _CATEGORY_TO_DIMENSION.get(sd.signal_category)


def build_credit_risk_response(db: Session, company: Company) -> CreditRiskResponse:
    rows = db.execute(
        select(GeneratedSignal, SignalDefinition, FinancialPeriod)
        .join(SignalDefinition, SignalDefinition.signal_def_id == GeneratedSignal.signal_def_id)
        .outerjoin(FinancialPeriod, FinancialPeriod.period_id == GeneratedSignal.period_id)
        .where(GeneratedSignal.company_id == company.company_id)
        .where(GeneratedSignal.is_published.is_(True))
        .order_by(GeneratedSignal.signal_score.desc().nullslast(), GeneratedSignal.created_at.desc())
    ).all()

    signals: list[CreditRiskSignal] = []
    highest_rank = 0

    for sig, sd, per in rows:
        dimension = _dimension_for(sig, sd)
        if dimension is None:
            continue
        signals.append(
            CreditRiskSignal(
                signal_id=sig.signal_id,
                signal_code=sd.signal_code,
                signal_name=sd.signal_name,
                signal_category=sd.signal_category,
                credit_dimension=dimension,
                direction=sig.signal_direction,
                severity=sig.severity,
                confidence_score=float(sig.confidence_score) if sig.confidence_score is not None else None,
                signal_score=float(sig.signal_score) if sig.signal_score is not None else None,
                headline=sig.headline,
                explanation=sig.explanation,
                period=period_brief(per),
                event_id=sig.event_id,
                created_at=sig.created_at,
            )
        )
        if sig.signal_direction in {SignalDirection.NEGATIVE, SignalDirection.MIXED}:
            rank = _SEVERITY_RANK.get(sig.severity, 0)
            if rank > highest_rank:
                highest_rank = rank

    overall = _RANK_TO_SEVERITY.get(highest_rank, SeverityLevel.LOW).value
    rationale: str | None = None
    if signals:
        top = signals[0]
        rationale = (
            f"{top.signal_name} flagged at severity {top.severity.value.lower()}"
            f"{' (auditor)' if top.credit_dimension == 'auditor' else ''}."
        )

    return CreditRiskResponse(
        company=company_brief(company),
        overall_risk=overall,  # type: ignore[arg-type]
        rationale=rationale,
        signals=signals,
    )
