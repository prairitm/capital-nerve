"""OpenAI Agents SDK + WebSearchTool runner for one (Company, PeriodSpec) pair.

Direct port of `experiment/6/src/ir_agent/agent.py`, with three changes:

1. The prompt is parametrised by an explicit `display_label` (e.g. `Q3
   FY2025-26`) so the agent searches for **that quarter** instead of the
   "latest" — the bulk ingestor enumerates every quarter explicitly.
2. The structured-output type is :class:`PeriodAssetSet`, which omits
   audio (the pipeline has no audio extractor) and adds an optional
   `annual_report` slot.
3. Annual periods (`PeriodSpec.is_annual`) skip the quarterly-results
   search and ask for the full annual report PDF instead.

This is the only module in the package that imports from `agents` (the
OpenAI Agents SDK). Other code consumes the returned `PeriodAssetSet`.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from app.core.config import settings
from app.core.env import ensure_openai_api_key
from app.services.ir_discovery.schemas import (
    CompanyRef,
    CompanyTarget,
    PeriodAssetSet,
    PeriodSpec,
)


logger = logging.getLogger(__name__)


_QUARTERLY_INSTRUCTIONS = """You are an investor-relations research agent for Indian-listed companies.

GOAL: For the given company AND THE EXACT QUARTER REQUESTED, find these IR assets:
  1. financial_report_pdf - the quarterly financial-results PDF for that quarter
  2. transcript           - the earnings/conference-call transcript PDF for that quarter
  3. presentation         - the investor / earnings-call presentation PDF for that quarter

STRATEGY:
  - Use `web_search` to locate the company's investor-relations (IR) page,
    then drill into THE SPECIFIC QUARTER passed in the user message.
  - Useful queries include:
      "<company name> investor relations"
      "<company name> <quarter label> results pdf"
      "<company name> <quarter label> earnings call transcript"
      "<company name> <quarter label> investor presentation pdf"
  - DO NOT fall back to a different quarter. If a particular asset is not
    available for the requested quarter, return null for that field. Never
    substitute a different quarter's PDF.

SOURCING RULES:
  - Prefer assets hosted on the company's own domain or on standard CDNs:
    .s3.amazonaws.com, .s3.ap-south-1.amazonaws.com, .blob.core.windows.net,
    .cloudfront.net, .akamaized.net, .azureedge.net.
  - BSE (bseindia.com) and NSE (nseindia.com / archives.nseindia.com)
    filings are an acceptable fallback for the results PDF, transcript,
    and presentation.
  - For each asset, return a DIRECT file link. The URL should end in `.pdf`,
    `.txt`, or `.md`. Never return a generic listing/landing page as the
    asset URL — put that in `source_page`.
  - If an asset genuinely cannot be located, set its field to null. NEVER
    fabricate or guess URLs.

OUTPUT:
  - Return only the structured `PeriodAssetSet` object.
  - `period` MUST echo the requested quarter label EXACTLY, in the form
    `Q{n} FY{yyyy}-{yy}` (e.g. `Q3 FY2025-26`). Never use 2-digit years or
    alternate spellings.
  - `annual_report` should be null for quarterly requests.
  - Populate `notes` with a 1-2 sentence summary of where you found things.
"""

_ANNUAL_INSTRUCTIONS = """You are an investor-relations research agent for Indian-listed companies.

GOAL: For the given company AND THE EXACT FISCAL YEAR REQUESTED, locate the
full annual report PDF (the document that includes the directors' report,
audited financial statements, MD&A, and notes — NOT a quarterly results
filing).

STRATEGY:
  - Use `web_search` to locate the company's annual report page for the
    requested FY label.
  - Prefer assets hosted on the company's own domain. BSE filings are an
    acceptable fallback when a direct download isn't available.

SOURCING RULES:
  - Direct PDF URL only — no landing pages.
  - URL must end in `.pdf` / `.txt` / `.md`.
  - If the annual report cannot be located, return null for `annual_report`.
    Never fabricate URLs.

OUTPUT:
  - Return only the structured `PeriodAssetSet` object.
  - `period` MUST echo the requested annual label EXACTLY.
  - Populate `annual_report` with the direct PDF URL when found.
  - Set `financial_report_pdf`, `transcript`, and `presentation` to null
    for annual requests.
  - Populate `notes` with a 1-2 sentence summary of where you found it.
"""


def _build_agent(period: PeriodSpec):
    """Lazy import of the OpenAI Agents SDK so unit tests that monkeypatch
    `find_period_assets` don't need the dep installed."""
    from agents import Agent, WebSearchTool  # type: ignore

    model = settings.IR_AGENT_MODEL or os.environ.get("IR_AGENT_MODEL", "gpt-5.5")
    instructions = _ANNUAL_INSTRUCTIONS if period.is_annual else _QUARTERLY_INSTRUCTIONS
    return Agent(
        name="IR Asset Finder",
        instructions=instructions,
        tools=[WebSearchTool(search_context_size="high")],
        output_type=PeriodAssetSet,
        model=model,
    )


def _user_prompt(company: CompanyTarget, period: PeriodSpec) -> str:
    parts = [f"Company: {company.company_name}"]
    if company.nse_symbol:
        parts.append(f"NSE symbol: {company.nse_symbol}")
    if company.investor_relations_url:
        parts.append(f"Known IR page: {company.investor_relations_url}")
    parts.append(
        f"Period (use this EXACT string in your `period` field): {period.display_label}"
    )
    parts.append(f"Period type: {period.period_type.value}")
    if period.is_annual:
        parts.append(
            f"Fiscal year window: {period.period_start.isoformat()} to "
            f"{period.period_end.isoformat()}"
        )
        parts.append("Find the full annual report PDF for this fiscal year.")
    else:
        parts.append(
            f"Quarter window: {period.period_start.isoformat()} to "
            f"{period.period_end.isoformat()}"
        )
        parts.append(
            "Find the financial-results PDF, concall transcript, and concall "
            "presentation for this exact quarter."
        )
    return "\n".join(parts)


async def find_period_assets(
    company: CompanyTarget,
    period: PeriodSpec,
    *,
    max_turns: int = 20,
) -> PeriodAssetSet:
    """Run the agent for one (company, period) pair and return the structured result.

    The bulk-ingest CLI calls this from inside an `asyncio.Semaphore` so
    concurrent calls stay below the configured limit.
    """
    from agents import Runner  # type: ignore

    ensure_openai_api_key()
    agent = _build_agent(period)
    prompt = _user_prompt(company, period)
    logger.debug("ir-agent prompt for %s / %s:\n%s", company.nse_symbol or company.company_name, period.display_label, prompt)
    result = await Runner.run(agent, prompt, max_turns=max_turns)
    output = result.final_output_as(PeriodAssetSet)

    # Always overwrite echoes with our canonical identity so the caller never
    # has to trust whatever the model said.
    output.company = CompanyRef(symbol=company.nse_symbol, name=company.company_name)
    output.period = period.display_label
    return output


__all__ = ["find_period_assets"]
