from __future__ import annotations

import os
from datetime import date
from typing import Literal
from urllib.parse import urlparse

try:
    from dotenv import load_dotenv
    from openai import OpenAI
    from pydantic import BaseModel, Field, field_validator, model_validator
except ImportError as exc:
    raise ImportError(
        "Missing dependency. Install with: "
        "pip install openai pydantic python-dotenv"
    ) from exc

try:
    import pandas as pd
except ImportError:
    pd = None

load_dotenv()

AssetType = Literal[
    "financial_result",
    "investor_presentation",
    "earnings_transcript",
]

ALLOWED_ASSET_TYPES: tuple[str, ...] = (
    "financial_result",
    "investor_presentation",
    "earnings_transcript",
)

ASSET_SORT_ORDER = {asset_type: index for index, asset_type in enumerate(ALLOWED_ASSET_TYPES)}
DEFAULT_MODEL = os.getenv("IR_AGENT_MODEL", "gpt-5.5")


class IrAssetMatch(BaseModel):
    asset_type: AssetType = Field(
        description=(
            "Document type: financial_result, investor_presentation, "
            "or earnings_transcript."
        )
    )
    title: str = Field(description="Human-readable document title.")
    url: str = Field(
        description=(
            "Best available URL for the asset. Prefer a direct .pdf URL. "
            "If no direct file URL exists, use the most specific source page."
        )
    )
    source_page: str | None = Field(
        default=None,
        description="Page where the asset link was discovered, if different from url.",
    )
    published_or_period_date: str | None = Field(
        default=None,
        description="Publication date or period date in YYYY-MM-DD format when known.",
    )
    period_label: str | None = Field(
        default=None,
        description="Period label such as Q1 FY2026-27 or FY2025-26 when known.",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence that this asset belongs to the requested company and timeframe.",
    )
    notes: str | None = Field(
        default=None,
        description="Brief sourcing or caveat note.",
    )

    @field_validator("url", "source_page")
    @classmethod
    def _validate_url(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("URL must be an absolute http(s) URL")
        return value

    @field_validator("published_or_period_date")
    @classmethod
    def _validate_optional_iso_date(cls, value: str | None) -> str | None:
        if value in (None, ""):
            return None
        date.fromisoformat(value)
        return value


class IrAssetSearchResult(BaseModel):
    company_url: str = Field(description="The company URL supplied by the user.")
    company_name: str | None = Field(default=None, description="Company name, if known.")
    timeframe_start: str = Field(description="Requested start date in YYYY-MM-DD format.")
    timeframe_end: str = Field(description="Requested end date in YYYY-MM-DD format.")
    matches: list[IrAssetMatch] = Field(
        default_factory=list,
        description="All matched IR assets in the requested timeframe.",
    )
    missing_asset_types: list[AssetType] = Field(
        default_factory=list,
        description="Asset types not found for the requested company/timeframe.",
    )
    notes: str | None = Field(
        default=None,
        description="Short summary of the search and any caveats.",
    )

    @field_validator("company_url")
    @classmethod
    def _validate_company_url(cls, value: str) -> str:
        value = value.strip()
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("COMPANY_URL must be an absolute http(s) URL")
        return value

    @field_validator("timeframe_start", "timeframe_end")
    @classmethod
    def _validate_iso_date(cls, value: str) -> str:
        date.fromisoformat(value)
        return value

    @model_validator(mode="after")
    def _validate_window_and_missing_types(self) -> "IrAssetSearchResult":
        if date.fromisoformat(self.timeframe_end) < date.fromisoformat(self.timeframe_start):
            raise ValueError("timeframe_end must be on or after timeframe_start")
        found = {match.asset_type for match in self.matches}
        missing = set(self.missing_asset_types)
        overlap = found & missing
        if overlap:
            raise ValueError(f"Asset types cannot be both found and missing: {sorted(overlap)}")
        return self


SYSTEM_PROMPT = """You are an investor-relations research agent.

Goal: find financial results, investor presentations, and earnings-call / conference-call transcripts for the exact company URL and date window requested.

Search rules:
- Treat the supplied company URL as the starting point and preferred source.
- Prefer assets hosted on the company domain or clearly linked official CDN domains.
- NSE and BSE filing pages are acceptable fallbacks for Indian-listed companies.
- Use other sources only when they are clearly official investor-relations sources for the same company.
- Prefer direct document URLs, especially .pdf links. If a direct URL is unavailable, return the most specific source page and explain why in notes.
- Reject assets that are clearly outside the requested date window.
- Do not substitute another company or another period.
- Do not fabricate URLs, dates, or period labels.
- If an asset type cannot be found, add it to missing_asset_types.
"""


def _validate_inputs(company_url: str, start_date: str, end_date: str) -> None:
    parsed = urlparse(company_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("company_url must be an absolute http(s) URL")
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if end < start:
        raise ValueError("end_date must be on or after start_date")


def find_ir_assets(
    *,
    company_url: str,
    company_name: str | None,
    start_date: str,
    end_date: str,
    model: str | None = None,
) -> IrAssetSearchResult:
    """Search for IR documents and return validated structured results."""
    _validate_inputs(company_url, start_date, end_date)
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set. Add it to your environment or .env file.")

    client = OpenAI()
    user_prompt = f"""
Company URL: {company_url}
Company name: {company_name or "unknown"}
Timeframe start: {start_date}
Timeframe end: {end_date}

Find these asset types for this exact company and timeframe:
1. financial_result
2. investor_presentation
3. earnings_transcript

Return every credible match. If multiple quarterly documents are in the window, return each one.
""".strip()

    response = client.responses.parse(
        model=model or os.getenv("IR_AGENT_MODEL", DEFAULT_MODEL),
        tools=[{"type": "web_search", "search_context_size": "high"}],
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        text_format=IrAssetSearchResult,
    )
    return response.output_parsed


def results_to_dataframe(result: IrAssetSearchResult):
    if pd is None:
        raise ImportError("pandas is required for results_df. Install with: pip install pandas")

    rows = [match.model_dump() for match in result.matches]
    columns = [
        "asset_type",
        "period_label",
        "published_or_period_date",
        "title",
        "url",
        "source_page",
        "confidence",
        "notes",
    ]
    df = pd.DataFrame(rows, columns=columns)
    if df.empty:
        return df

    df["_date_sort"] = pd.to_datetime(df["published_or_period_date"], errors="coerce")
    df["_asset_sort"] = df["asset_type"].map(ASSET_SORT_ORDER).fillna(99)
    df = df.sort_values(
        by=["_date_sort", "_asset_sort", "asset_type", "title"],
        ascending=[False, True, True, True],
        na_position="last",
    )
    return df.drop(columns=["_date_sort", "_asset_sort"]).reset_index(drop=True)


def summarize_result(result: IrAssetSearchResult) -> None:
    print(f"Company: {result.company_name or '(unknown)'}")
    print(f"URL: {result.company_url}")
    print(f"Window: {result.timeframe_start} to {result.timeframe_end}")
    print(f"Matches: {len(result.matches)}")
    missing = ", ".join(result.missing_asset_types) or "none"
    print(f"Missing asset types: {missing}")
    if result.notes:
        print(f"Notes: {result.notes}")
