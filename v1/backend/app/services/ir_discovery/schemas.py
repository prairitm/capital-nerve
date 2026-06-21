"""Pydantic / dataclass shapes for the bulk-ingest pipeline.

`PeriodAssetSet` is the structured-output type the OpenAI Agents SDK forces
the agent to return. `PeriodSpec` is the internal representation of one
quarter or annual reporting window — the CLI builds a list of these and
loops over them with the agent.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from pydantic import BaseModel, Field

from app.db.enums import DocumentType, EventType, PeriodType


# ---------------------------------------------------------------------------
# Internal (CLI-side) shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PeriodSpec:
    """One reporting window the bulk ingestor will look up.

    `period_type=QUARTERLY` requires `quarter` in 1..4. `period_type=ANNUAL`
    sets `quarter=None` and represents the full FY ending 31 March of
    `fy_year + 1`.
    """

    fy_year: int
    period_type: PeriodType
    quarter: Optional[int]
    period_start: date
    period_end: date
    fy_label: str
    display_label: str

    @property
    def is_quarterly(self) -> bool:
        return self.period_type == PeriodType.QUARTERLY

    @property
    def is_annual(self) -> bool:
        return self.period_type == PeriodType.ANNUAL

    @property
    def slug(self) -> str:
        """Filesystem segment for this period, e.g. ``Q3_FY2025-26``."""
        from app.services.ingest_common import period_slug_from_display_label

        return period_slug_from_display_label(self.display_label)


@dataclass(frozen=True)
class CompanyTarget:
    """Lightweight projection of a `Company` row for the agent + storage layer.

    We do not hand a SQLAlchemy ORM instance to the async agent — async code
    can outlive the originating session and lazy-load attributes against a
    closed connection. This dataclass is the safe wire format.
    """

    company_id: int
    company_name: str
    nse_symbol: Optional[str]
    bse_code: Optional[str]
    investor_relations_url: Optional[str] = None


# Map a PeriodAssetSet field name to the corresponding (EventType, DocumentType)
# pair. The keys mirror the field names on `PeriodAssetSet` below.
DOC_TYPE_BY_ASSET_KEY: dict[str, tuple[EventType, DocumentType]] = {
    "financial_report_pdf": (EventType.QUARTERLY_RESULT, DocumentType.FINANCIAL_RESULT),
    "transcript": (EventType.CONCALL_TRANSCRIPT, DocumentType.CONCALL_TRANSCRIPT),
    "presentation": (
        EventType.INVESTOR_PRESENTATION,
        DocumentType.INVESTOR_PRESENTATION,
    ),
    "annual_report": (EventType.ANNUAL_REPORT, DocumentType.ANNUAL_REPORT),
}


# ---------------------------------------------------------------------------
# Agent-facing structured-output shapes
# ---------------------------------------------------------------------------


class CompanyRef(BaseModel):
    """Identifies the company the agent is researching."""

    symbol: Optional[str] = Field(
        default=None,
        description="NSE/BSE ticker symbol, e.g. 'RELIANCE'.",
    )
    name: str = Field(
        description="Full legal company name, e.g. 'Reliance Industries Ltd.'.",
    )


class AssetMatch(BaseModel):
    """A single resolved investor-relations asset."""

    url: str = Field(
        description=(
            "Direct file URL for the asset (must end in .pdf / .txt / .md). "
            "Never a landing page."
        ),
    )
    title: Optional[str] = Field(
        default=None,
        description="Human-readable title for the asset, if available.",
    )
    source_page: Optional[str] = Field(
        default=None,
        description="The page where this asset link was discovered.",
    )


class PeriodAssetSet(BaseModel):
    """The IR assets for a single (company, period) pair.

    Identical layout to the original `experiment/6` `IrAssetSet`, but:

    - `audio` is removed (the pipeline has no audio extractor).
    - The `period` field is a structured echo of the request — the agent
      MUST return the same period it was asked about. We cross-check this
      in `ingest_one` to detect drift.
    - `annual_report` is added so a single agent call can pull the FY
      results PDF when the requested period is annual or covers Q4.
    """

    company: CompanyRef = Field(
        description="The company this asset bundle belongs to.",
    )
    period: str = Field(
        description=(
            "The period the agent resolved, in the same format as the "
            "request, e.g. 'Q3 FY2025-26' or 'FY2024-25'."
        ),
    )
    financial_report_pdf: Optional[AssetMatch] = Field(
        default=None,
        description="Quarterly / annual financial-results PDF for the period.",
    )
    transcript: Optional[AssetMatch] = Field(
        default=None,
        description="Earnings/conference-call transcript PDF for the period.",
    )
    presentation: Optional[AssetMatch] = Field(
        default=None,
        description="Investor / earnings-call presentation PDF for the period.",
    )
    annual_report: Optional[AssetMatch] = Field(
        default=None,
        description=(
            "Full annual report PDF. Set only when the requested period is "
            "annual (or the agent additionally found one for the FY whose Q4 "
            "is being requested)."
        ),
    )
    notes: Optional[str] = Field(
        default=None,
        description="Short reasoning trail explaining how the assets were located.",
    )


__all__ = [
    "AssetMatch",
    "CompanyRef",
    "CompanyTarget",
    "DOC_TYPE_BY_ASSET_KEY",
    "PeriodAssetSet",
    "PeriodSpec",
]
