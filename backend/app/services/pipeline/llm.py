"""LLM-backed structured extraction.

This module hides the choice of provider behind a single interface so the rest
of the pipeline never imports `anthropic` or `openai` directly. Three providers
are wired in:

- `MockProvider` — deterministic regex parser. The default; lets the pipeline
  run end-to-end with zero external dependencies. Useful for tests, CI, and
  local development without an API key.
- `AnthropicProvider` — calls `claude-*` with a structured JSON prompt.
  Activated by setting `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY` in env.
- `OpenAIProvider` — calls OpenAI chat completions with the same JSON prompt.
  Activated by setting `LLM_PROVIDER=openai` and `OPENAI_API_KEY` in env.

All providers return the same shape: `ExtractionResult`. Pipeline downstream
stages cannot tell which provider produced the data.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Protocol

from app.core.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data shapes returned to the rest of the pipeline
# ---------------------------------------------------------------------------


@dataclass
class ExtractedLineItem:
    """One structured numeric line item extracted from the document."""

    normalized_code: str  # MUST match a `financial_line_item_definitions.normalized_code`
    raw_label: str  # what the document called it (e.g. "Revenue from operations")
    value: float  # numeric value in `unit`
    unit: str = "crore"  # default reporting unit in India is INR crore
    page_number: int | None = None
    source_text: str | None = None  # quoted source line — surfaces as evidence
    confidence: float = 90.0  # 0..100


@dataclass
class ExtractionResult:
    """Aggregate output of one extraction call for one document."""

    items: list[ExtractedLineItem]
    model_name: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    overall_confidence: float = 90.0
    raw_response: str | None = None
    notes: list[str] = field(default_factory=list)


class LLMProvider(Protocol):
    """Anything that can turn `DocumentPage` text into `ExtractedLineItem`s."""

    name: str

    def extract_financial_facts(
        self, *, pages: list[tuple[int, str]], document_title: str
    ) -> ExtractionResult: ...


# ---------------------------------------------------------------------------
# Provider: deterministic mock
# ---------------------------------------------------------------------------


# Mapping from common report labels to canonical line-item codes used by
# `financial_line_item_definitions`. The order matters: more specific labels
# must come before generic ones so "EBITDA margin" doesn't accidentally match
# "EBITDA".
_LABEL_PATTERNS: list[tuple[re.Pattern[str], str, str, str]] = [
    # ---------------- P&L ----------------
    (re.compile(r"\bEBITDA\s*margin\b", re.IGNORECASE), "ebitda_margin", "EBITDA Margin", "%"),
    (re.compile(r"\bEBITDA\b", re.IGNORECASE), "ebitda", "EBITDA", "crore"),
    (
        re.compile(r"revenue\s+from\s+operations|revenue\s+from\s+ops", re.IGNORECASE),
        "revenue_from_operations",
        "Revenue from Operations",
        "crore",
    ),
    (re.compile(r"\bother\s+income\b", re.IGNORECASE), "other_income", "Other Income", "crore"),
    (re.compile(r"\btotal\s+income\b", re.IGNORECASE), "total_income", "Total Income", "crore"),
    (
        re.compile(r"employee\s+benefit(?:s)?\s+expense", re.IGNORECASE),
        "employee_cost",
        "Employee Benefit Expenses",
        "crore",
    ),
    (re.compile(r"\bfinance\s+cost", re.IGNORECASE), "finance_cost", "Finance Costs", "crore"),
    (
        re.compile(r"depreciation(?:\s+&|\s+and)?\s+amortisation", re.IGNORECASE),
        "depreciation",
        "Depreciation & Amortisation",
        "crore",
    ),
    (re.compile(r"\bother\s+expenses\b", re.IGNORECASE), "other_expenses", "Other Expenses", "crore"),
    (
        re.compile(r"\bexceptional\s+item(?:s)?\b", re.IGNORECASE),
        "exceptional_items",
        "Exceptional Items",
        "crore",
    ),
    (
        re.compile(r"\bcost\s+of\s+goods\s+sold\b|\bCOGS\b", re.IGNORECASE),
        "cogs",
        "Cost of Goods Sold",
        "crore",
    ),
    (re.compile(r"profit\s+before\s+tax|\bPBT\b", re.IGNORECASE), "pbt", "Profit Before Tax", "crore"),
    (re.compile(r"tax\s+expense", re.IGNORECASE), "tax_expense", "Tax Expense", "crore"),
    (re.compile(r"profit\s+after\s+tax|\bPAT\b", re.IGNORECASE), "pat", "Profit After Tax", "crore"),
    (re.compile(r"\bEPS\s*\(?\s*diluted\)?\b|\bdiluted\s+EPS\b", re.IGNORECASE), "eps_diluted", "EPS (Diluted)", "Rs"),
    (re.compile(r"\bEPS\b", re.IGNORECASE), "eps_basic", "EPS (Basic)", "Rs"),
    # ---------------- Cash flow ----------------
    (
        re.compile(r"cash\s+(?:flow|generated)\s+from\s+(?:operating|operations)", re.IGNORECASE),
        "cfo",
        "Cash Flow from Operations",
        "crore",
    ),
    (
        re.compile(r"\bcapital\s+expenditure|\bcapex\b", re.IGNORECASE),
        "capex_ppe",
        "Capex (PPE)",
        "crore",
    ),
    (
        re.compile(r"\bdividend(?:s)?\s+paid\b", re.IGNORECASE),
        "dividend_paid",
        "Dividends Paid",
        "crore",
    ),
    (
        re.compile(r"\binterest\s+paid\b", re.IGNORECASE),
        "interest_paid",
        "Interest Paid",
        "crore",
    ),
    # ---------------- Working capital ----------------
    (
        re.compile(r"trade\s+receivable(?:s)?", re.IGNORECASE),
        "trade_receivables",
        "Trade Receivables",
        "crore",
    ),
    (
        re.compile(r"\binventory\b|\binventories\b", re.IGNORECASE),
        "inventory",
        "Inventory",
        "crore",
    ),
    (
        re.compile(r"trade\s+payable(?:s)?", re.IGNORECASE),
        "trade_payables",
        "Trade Payables",
        "crore",
    ),
    # ---------------- Balance sheet ----------------
    (
        re.compile(r"short[-\s]term\s+borrowing(?:s)?", re.IGNORECASE),
        "short_term_borrowings",
        "Short-Term Borrowings",
        "crore",
    ),
    (
        re.compile(r"long[-\s]term\s+borrowing(?:s)?", re.IGNORECASE),
        "long_term_borrowings",
        "Long-Term Borrowings",
        "crore",
    ),
    (
        re.compile(r"lease\s+liabilit(?:y|ies)", re.IGNORECASE),
        "lease_liabilities",
        "Lease Liabilities",
        "crore",
    ),
    (
        re.compile(r"cash\s+(?:and|&)\s+(?:cash\s+)?equivalent(?:s)?", re.IGNORECASE),
        "cash_and_equivalents",
        "Cash & Equivalents",
        "crore",
    ),
    (
        re.compile(r"current\s+investment(?:s)?", re.IGNORECASE),
        "current_investments",
        "Current Investments",
        "crore",
    ),
    (
        re.compile(r"shareholders[\u2019']?\s+equity|total\s+equity", re.IGNORECASE),
        "shareholders_equity",
        "Shareholders' Equity",
        "crore",
    ),
    (
        re.compile(r"total\s+assets", re.IGNORECASE),
        "total_assets",
        "Total Assets",
        "crore",
    ),
    # ---------------- Order book / guidance ----------------
    (
        re.compile(r"closing\s+order\s+book|\border\s+book\s+at\s+(?:end|close)", re.IGNORECASE),
        "closing_order_book",
        "Closing Order Book",
        "crore",
    ),
    (
        re.compile(r"order\s+inflow|\bnew\s+orders\b", re.IGNORECASE),
        "order_inflow",
        "Order Inflow",
        "crore",
    ),
]

# Pulls a numeric out of strings like "Rs 900.4 Cr", "26.5%", "(1,234.5)", "₹1,200"
_NUMBER_RE = re.compile(
    r"""
    (?:Rs\.?|₹|INR)?\s*                # optional currency prefix
    \(?                                  # optional opening paren (negative)
    (?P<num>-?[\d,]*\d(?:\.\d+)?)        # digits, commas, optional decimal
    \)?                                  # optional closing paren
    \s*(?:%|bps|x|Cr(?:ore)?|lakh|mn|million|bn|billion)?  # optional unit
    """,
    re.VERBOSE | re.IGNORECASE,
)


class MockProvider:
    """Best-effort regex-based extractor.

    Walks every page line by line, matches one of the known labels, and picks
    the first plausible number on the same line. This is good enough to give
    the downstream pipeline real numbers when no LLM is configured.
    """

    name = "mock-regex-v1"

    def extract_financial_facts(
        self, *, pages: list[tuple[int, str]], document_title: str
    ) -> ExtractionResult:
        seen: dict[str, ExtractedLineItem] = {}
        notes: list[str] = []
        for page_no, text in pages:
            for line in text.splitlines():
                line_clean = line.strip()
                if not line_clean or len(line_clean) > 240:
                    continue
                for pattern, code, raw_label, unit in _LABEL_PATTERNS:
                    if not pattern.search(line_clean):
                        continue
                    value = _extract_number(line_clean, after=pattern)
                    if value is None:
                        continue
                    # Prefer the first hit on the earliest page — quarterly
                    # results typically print the headline number once at the
                    # top of the P&L.
                    if code in seen:
                        continue
                    seen[code] = ExtractedLineItem(
                        normalized_code=code,
                        raw_label=raw_label,
                        value=value,
                        unit=unit,
                        page_number=page_no,
                        source_text=line_clean,
                        confidence=78.0,  # honest about being a regex
                    )
                    break

        if not seen:
            notes.append("Mock extractor found no recognisable financial line items.")

        return ExtractionResult(
            items=list(seen.values()),
            model_name=self.name,
            overall_confidence=78.0 if seen else 40.0,
            notes=notes,
        )


def _extract_number(line: str, *, after: re.Pattern[str]) -> float | None:
    """Return the first numeric token AFTER the matching label."""
    match = after.search(line)
    if not match:
        return None
    tail = line[match.end():]
    # Walk through every number candidate so we can skip year-like junk
    # ("2025", "Q4 FY26") that follows the label before the real value.
    for m in _NUMBER_RE.finditer(tail):
        raw = (m.group("num") or "").replace(",", "")
        if not raw:
            continue
        try:
            val = float(raw)
        except ValueError:
            continue
        # Treat (123) as negative — accountants love brackets.
        if "(" in m.group(0) and ")" in m.group(0):
            val = -abs(val)
        # Drop calendar years which often trail labels in PDF dumps.
        if 1900 <= val <= 2099 and val == int(val):
            continue
        return val
    return None


# ---------------------------------------------------------------------------
# Shared LLM prompt + helpers (Anthropic / OpenAI)
# ---------------------------------------------------------------------------


_EXTRACTION_SYSTEM_PROMPT = """You are CapitalNerve's financial document extractor.

Return ONLY valid JSON matching this schema (no prose, no markdown fences):

{
  "items": [
    {
      "normalized_code": "<one of: revenue_from_operations, other_income, total_income, employee_cost, finance_cost, depreciation, other_expenses, cogs, exceptional_items, ebitda, ebitda_margin, ebit, pbt, tax_expense, pat, eps_basic, eps_diluted, cfo, capex_ppe, capex_intangibles, dividend_paid, interest_paid, borrowings_raised, trade_receivables, inventory, trade_payables, current_assets, current_liabilities, short_term_borrowings, long_term_borrowings, lease_liabilities, cash_and_equivalents, current_investments, share_capital, other_equity, shareholders_equity, total_assets, total_liabilities, promoter_holding_pct, promoter_pledge_pct, fii_holding_pct, dii_holding_pct, public_holding_pct, revenue_guidance_lower, revenue_guidance_upper, ebitda_margin_guidance_lower, ebitda_margin_guidance_upper, opening_order_book, closing_order_book, order_inflow, executed_orders, cancelled_orders, top_customer_orders>",
      "raw_label": "<the exact label as printed in the document>",
      "value": <number>,
      "unit": "<crore | % | Rs | bps | days | x>",
      "page_number": <integer page index, 1-based>,
      "source_text": "<the source line, verbatim>",
      "confidence": <0..100>
    }
  ],
  "overall_confidence": <0..100>,
  "notes": ["<optional caveats>"]
}

Rules:
- Only include line items present in the document. Skip anything you're unsure of.
- Values are in INR crore unless the document explicitly says otherwise.
- For percentages (margins, holdings, guidance ranges) use unit "%".
- For EPS in rupees, use unit "Rs".
- Shareholding pattern values (promoter / FII / DII / public / pledge) are percentages (0..100).
- Guidance fields: emit `revenue_guidance_lower`/`upper` (and `ebitda_margin_guidance_lower`/`upper`) only when management gives an explicit range; if it's a point estimate, set lower = upper = the point.
- Order-book fields are in INR crore unless the document quotes a different unit.
- Negative values use a leading minus, not parentheses.
"""


def _build_extraction_user_message(
    *, pages: list[tuple[int, str]], document_title: str
) -> str:
    joined = "\n\n".join(f"--- PAGE {p} ---\n{t}" for p, t in pages[:30])
    return (
        f"Document title: {document_title}\n"
        f"Total pages: {len(pages)}\n\n"
        f"Extract the financial line items.\n\n{joined}"
    )


def _parse_llm_json_response(raw: str) -> tuple[list[ExtractedLineItem], float, list[str]]:
    """Defensive parser — strips markdown fences and tolerates trailing prose."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    m = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not m:
        return [], 0.0, ["LLM returned no JSON object."]
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError as exc:
        return [], 0.0, [f"LLM JSON parse failed: {exc}"]
    items: list[ExtractedLineItem] = []
    for entry in data.get("items", []):
        try:
            items.append(
                ExtractedLineItem(
                    normalized_code=str(entry["normalized_code"]).strip(),
                    raw_label=str(entry.get("raw_label", entry["normalized_code"])),
                    value=float(entry["value"]),
                    unit=str(entry.get("unit", "crore")),
                    page_number=int(entry["page_number"]) if entry.get("page_number") else None,
                    source_text=entry.get("source_text"),
                    confidence=float(entry.get("confidence", 85.0)),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Skipping malformed item from LLM: %s (%s)", entry, exc)
    overall = float(data.get("overall_confidence", 85.0))
    notes = list(data.get("notes", []))
    return items, overall, notes


def _fallback_to_mock(
    *,
    pages: list[tuple[int, str]],
    document_title: str,
    provider_label: str,
    exc: Exception,
) -> ExtractionResult:
    """Fall back to the regex extractor when an upstream LLM call fails.

    In production we re-raise instead: a silent fallback would hide upstream
    outages and ship low-confidence cards that look identical to real
    extractions. The pipeline runner catches the exception and surfaces the
    job in the Review Queue.
    """
    if settings.is_production:
        raise exc
    logger.exception("%s call failed; falling back to mock", provider_label)
    mock = MockProvider().extract_financial_facts(pages=pages, document_title=document_title)
    mock.notes.append(f"{provider_label} call failed: {exc}; used mock extractor instead.")
    return mock


# ---------------------------------------------------------------------------
# Provider: Anthropic Claude (structured output)
# ---------------------------------------------------------------------------


class AnthropicProvider:
    """Calls Claude with the system prompt above and parses JSON back."""

    name: str

    def __init__(self, model: str, api_key: str) -> None:
        # Imported lazily so installs that never set ANTHROPIC_API_KEY don't
        # pay the import cost.
        from anthropic import Anthropic  # type: ignore

        self._client = Anthropic(api_key=api_key)
        self._model = model
        self.name = f"anthropic:{model}"

    def extract_financial_facts(
        self, *, pages: list[tuple[int, str]], document_title: str
    ) -> ExtractionResult:
        user_message = _build_extraction_user_message(
            pages=pages, document_title=document_title
        )

        try:
            resp = self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                system=_EXTRACTION_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
        except Exception as exc:
            return _fallback_to_mock(
                pages=pages,
                document_title=document_title,
                provider_label="Anthropic",
                exc=exc,
            )

        text_chunks = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
        raw = "".join(text_chunks).strip()
        items, overall, notes = _parse_llm_json_response(raw)

        return ExtractionResult(
            items=items,
            model_name=self.name,
            input_tokens=getattr(resp.usage, "input_tokens", None),
            output_tokens=getattr(resp.usage, "output_tokens", None),
            overall_confidence=overall,
            raw_response=raw,
            notes=notes,
        )


# ---------------------------------------------------------------------------
# Provider: OpenAI (structured output)
# ---------------------------------------------------------------------------


class OpenAIProvider:
    """Calls OpenAI chat completions with the shared extraction prompt."""

    name: str

    def __init__(self, model: str, api_key: str) -> None:
        from openai import OpenAI  # type: ignore

        self._client = OpenAI(api_key=api_key)
        self._model = model
        self.name = f"openai:{model}"

    def extract_financial_facts(
        self, *, pages: list[tuple[int, str]], document_title: str
    ) -> ExtractionResult:
        user_message = _build_extraction_user_message(
            pages=pages, document_title=document_title
        )

        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                max_tokens=4096,
                messages=[
                    {"role": "system", "content": _EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
            )
        except Exception as exc:
            return _fallback_to_mock(
                pages=pages,
                document_title=document_title,
                provider_label="OpenAI",
                exc=exc,
            )

        raw = (resp.choices[0].message.content or "").strip()
        items, overall, notes = _parse_llm_json_response(raw)
        usage = resp.usage

        return ExtractionResult(
            items=items,
            model_name=self.name,
            input_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
            output_tokens=getattr(usage, "completion_tokens", None) if usage else None,
            overall_confidence=overall,
            raw_response=raw,
            notes=notes,
        )


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------


def get_provider() -> LLMProvider:
    provider_name = (settings.LLM_PROVIDER or "mock").lower()
    if provider_name == "anthropic":
        api_key = settings.ANTHROPIC_API_KEY or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            if settings.is_production:
                raise RuntimeError(
                    "LLM_PROVIDER=anthropic requires ANTHROPIC_API_KEY in production."
                )
            logger.warning(
                "LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set; using mock extractor."
            )
            return MockProvider()
        return AnthropicProvider(model=settings.LLM_MODEL, api_key=api_key)
    if provider_name == "openai":
        api_key = settings.OPENAI_API_KEY or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            if settings.is_production:
                raise RuntimeError(
                    "LLM_PROVIDER=openai requires OPENAI_API_KEY in production."
                )
            logger.warning(
                "LLM_PROVIDER=openai but OPENAI_API_KEY is not set; using mock extractor."
            )
            return MockProvider()
        return OpenAIProvider(model=settings.LLM_MODEL, api_key=api_key)
    if settings.is_production:
        raise RuntimeError(
            "APP_ENV=production cannot use LLM_PROVIDER=mock. "
            "Set LLM_PROVIDER=anthropic or openai with a valid API key."
        )
    return MockProvider()
