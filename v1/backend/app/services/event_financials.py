"""Financial snapshot rows for a single reporting period (event drill-down)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.master import FinancialPeriod
from app.schemas.common import FinancialSnapshotRow
from app.services.financial_snapshot import SNAPSHOT_METRICS, build_financial_snapshot

_SNAPSHOT_METRICS = SNAPSHOT_METRICS


def build_financial_snapshot_for_period(
    db: Session,
    company_id: int,
    period: FinancialPeriod | None,
) -> list[FinancialSnapshotRow]:
    """Current period vs same quarter prior year."""
    return build_financial_snapshot(db, company_id=company_id, period=period)
