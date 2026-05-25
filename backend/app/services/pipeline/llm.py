"""LLM-backed structured extraction.

This module hides the choice of provider behind a single interface so the rest
of the pipeline never imports `anthropic` or `openai` directly. Three providers
are wired in:

- `MockProvider` — deterministic regex parser. The default; lets the pipeline
  run end-to-end with zero external dependencies. Useful for tests, CI, and
  local development without an API key.
- `AnthropicProvider` — calls `claude-*` with **tool use** so the model is
  forced to emit a JSON Schema-validated payload. Temperature is pinned to 0
  on models that still accept it; omitted on Opus 4.7+ (API rejects it).
  Multimodal: rendered page PNGs are sent alongside the text so the model
  reads tabular Indian financial-result PDFs from the image, not from pypdf's
  variable text dump.
- `OpenAIProvider` — calls OpenAI chat completions with the same JSON schema
  via `response_format={"type":"json_schema","strict":true}` and
  `temperature=0` + `seed`. Same multimodal contract as Anthropic.

All providers return the same shape: `ExtractionResult`. Pipeline downstream
stages cannot tell which provider produced the data.

Determinism contract: given the same (document bytes, prompt version, model,
seed, parser version) the providers return the same `ExtractionResult`. The
extraction stage exploits this with a request-hash cache on
`extraction_jobs.request_hash` so re-extract is a replay, not a re-call.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.core.config import settings

logger = logging.getLogger(__name__)


# Bump whenever the prompt / schema changes in a way that should invalidate the
# extraction cache on ``extraction_jobs.request_hash``. The extraction stage
# folds this into the cache key.
PROMPT_VERSION = "extract.v2"


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
    # Stamped onto ``extraction_jobs`` for the request-hash cache.
    temperature: float | None = None
    seed: int | None = None
    provider_used: str | None = None


@dataclass
class ProviderPage:
    """One page handed to the LLM provider: text + optional rendered image."""

    page_number: int
    text: str
    image_bytes: bytes | None = None


class LLMProvider(Protocol):
    """Anything that can turn `ProviderPage`s into `ExtractedLineItem`s."""

    name: str

    def extract_financial_facts(
        self, *, pages: list[ProviderPage], document_title: str
    ) -> ExtractionResult: ...


# ---------------------------------------------------------------------------
# JSON Schema — the single source of truth for structured-output mode.
# Both Anthropic tool_use and OpenAI strict json_schema consume this dict so
# prompt and validation can never drift relative to each other.
# ---------------------------------------------------------------------------


_NORMALIZED_CODES: tuple[str, ...] = (
    "revenue_from_operations",
    "other_income",
    "total_income",
    "employee_cost",
    "finance_cost",
    "depreciation",
    "other_expenses",
    "cogs",
    "exceptional_items",
    "ebitda",
    "ebitda_margin",
    "ebit",
    "pbt",
    "tax_expense",
    "pat",
    "eps_basic",
    "eps_diluted",
    "cfo",
    "capex_ppe",
    "capex_intangibles",
    "dividend_paid",
    "dividend_per_share",
    "interest_paid",
    "borrowings_raised",
    "trade_receivables",
    "inventory",
    "trade_payables",
    "current_assets",
    "current_liabilities",
    "short_term_borrowings",
    "long_term_borrowings",
    "lease_liabilities",
    "cash_and_equivalents",
    "current_investments",
    "share_capital",
    "other_equity",
    "shareholders_equity",
    "total_assets",
    "total_liabilities",
    "promoter_holding_pct",
    "promoter_pledge_pct",
    "fii_holding_pct",
    "dii_holding_pct",
    "public_holding_pct",
    "revenue_guidance_lower",
    "revenue_guidance_upper",
    "ebitda_margin_guidance_lower",
    "ebitda_margin_guidance_upper",
    "opening_order_book",
    "closing_order_book",
    "order_inflow",
    "executed_orders",
    "cancelled_orders",
    "top_customer_orders",
    "new_order_value",
    "acquisition_value",
    "revenue_contribution_pct",
    "new_capacity",
    "existing_capacity",
    "capacity_utilization_pct",
    "tam_market_size",
    "tam_market_size_prior",
    "high_margin_revenue_pct",
    "top_client_revenue_pct",
    "region_revenue_pct",
    "management_target_value",
    "primary_segment_revenue",
    "primary_segment_ebit",
    "share_price_close",
    "market_cap",
)

# Units the extraction stage accepts. ``validators.canonicalize_units`` maps
# common variants ("Cr", "INR cr", "Rs.") onto these canonical forms before
# the allow-list is enforced.
_ALLOWED_UNITS: tuple[str, ...] = ("crore", "%", "Rs", "bps", "days", "x")


_EXTRACTION_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["items", "overall_confidence", "notes"],
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "normalized_code",
                    "raw_label",
                    "value",
                    "unit",
                    "page_number",
                    "source_text",
                    "confidence",
                ],
                "properties": {
                    "normalized_code": {"type": "string", "enum": list(_NORMALIZED_CODES)},
                    "raw_label": {"type": "string"},
                    "value": {"type": "number"},
                    "unit": {"type": "string", "enum": list(_ALLOWED_UNITS)},
                    "page_number": {"type": "integer", "minimum": 1},
                    "source_text": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 100},
                },
            },
        },
        "overall_confidence": {"type": "number", "minimum": 0, "maximum": 100},
        "notes": {"type": "array", "items": {"type": "string"}},
    },
}


# ---------------------------------------------------------------------------
# Regex patterns — shared by MockProvider and quarter_column heuristics.
# ---------------------------------------------------------------------------


# Mapping from common report labels to canonical line-item codes used by
# `financial_line_item_definitions`. The order matters: more specific labels
# must come before generic ones so "EBITDA margin" doesn't accidentally match
# "EBITDA".
_LABEL_PATTERNS: list[tuple[re.Pattern[str], str, str, str]] = [
    # ---------------- P&L ----------------
    (re.compile(r"\bEBITDA\s*margin\b", re.IGNORECASE), "ebitda_margin", "EBITDA Margin", "%"),
    (re.compile(r"\bEBITDA\b", re.IGNORECASE), "ebitda", "EBITDA", "crore"),
    (re.compile(r"\bEBIT\b", re.IGNORECASE), "ebit", "EBIT", "crore"),
    (
        re.compile(r"\bgross\s+revenue\b", re.IGNORECASE),
        "revenue_from_operations",
        "Gross Revenue",
        "crore",
    ),
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
    (re.compile(r"\bdepreciation\b", re.IGNORECASE), "depreciation", "Depreciation", "crore"),
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


def _format_value_for_source_quote(value: float, unit: str) -> str:
    """Document-style number for evidence quotes (label + this value only)."""
    u = unit.strip().lower()
    if u == "%":
        return f"{value:.1f}%"
    if u == "bps":
        return f"{value:+.0f} bps"
    if u in ("rs", "inr"):
        if abs(value - round(value)) < 1e-6:
            return f"Rs {int(round(value)):,}"
        return f"Rs {value:,.2f}".rstrip("0").rstrip(".")
    if abs(value - round(value)) < 1e-6:
        return f"{int(round(value)):,}"
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    whole, _, frac = text.partition(".")
    return f"{int(whole):,}.{frac}" if frac else f"{int(whole):,}"


def _source_quote(raw_label: str, value: float, unit: str) -> str:
    """Single-value excerpt for evidence — not a full multi-column table row."""
    return f"{raw_label} {_format_value_for_source_quote(value, unit)}"


# ---------------------------------------------------------------------------
# Provider: deterministic mock
# ---------------------------------------------------------------------------


class MockProvider:
    """Best-effort regex-based extractor.

    Walks every page line by line, matches one of the known labels, and picks
    the first plausible number on the same line. This is good enough to give
    the downstream pipeline real numbers when no LLM is configured.
    """

    name = "mock-regex-v1"

    def extract_financial_facts(
        self, *, pages: list[ProviderPage], document_title: str
    ) -> ExtractionResult:
        del document_title
        seen: dict[str, ExtractedLineItem] = {}
        notes: list[str] = []
        for page in pages:
            for line in (page.text or "").splitlines():
                line_clean = line.strip()
                if not line_clean or len(line_clean) > 240:
                    continue
                for pattern, code, raw_label, unit in _LABEL_PATTERNS:
                    if not pattern.search(line_clean):
                        continue
                    value = _extract_number(line_clean, after=pattern)
                    if value is None:
                        continue
                    if code in seen:
                        continue
                    seen[code] = ExtractedLineItem(
                        normalized_code=code,
                        raw_label=raw_label,
                        value=value,
                        unit=unit,
                        page_number=page.page_number,
                        source_text=_source_quote(raw_label, value, unit),
                        confidence=78.0,  # honest about being a regex
                    )
                    break

        if not seen:
            notes.append("Mock extractor found no recognisable financial line items.")

        items = _finalize_quarter_items(
            list(seen.values()),
            pages=[(p.page_number, p.text or "") for p in pages],
        )
        return ExtractionResult(
            items=items,
            model_name=self.name,
            overall_confidence=78.0 if items else 40.0,
            notes=notes,
            temperature=0.0,
            seed=None,
            provider_used="mock",
        )


def _extract_number(line: str, *, after: re.Pattern[str]) -> float | None:
    """Return the first numeric token AFTER the matching label."""
    match = after.search(line)
    if not match:
        return None
    tail = line[match.end():]
    for m in _NUMBER_RE.finditer(tail):
        raw = (m.group("num") or "").replace(",", "")
        if not raw:
            continue
        try:
            val = float(raw)
        except ValueError:
            continue
        if "(" in m.group(0) and ")" in m.group(0):
            val = -abs(val)
        if 1900 <= val <= 2099 and val == int(val):
            continue
        return val
    return None


# ---------------------------------------------------------------------------
# Shared LLM prompt + multimodal helpers (Anthropic / OpenAI)
# ---------------------------------------------------------------------------


_EXTRACTION_SYSTEM_PROMPT = """You are CapitalNerve's financial document extractor.

You will receive the source document as a sequence of page images (rendered at
200 DPI) accompanied by the OCR text of each page. Trust the IMAGE for numeric
values when text and image disagree — the text comes from pypdf and is known
to mis-order columns on stacked-table layouts.

Emit the result by calling the `emit_financial_facts` tool (Anthropic) /
returning the structured JSON object (OpenAI). The schema is enforced
server-side; only the values you fill in are up to you.

Rules:
- Only include line items present in the document. Skip anything you're unsure of.
- Values are in INR crore unless the document explicitly says otherwise.
- For percentages (margins, holdings, guidance ranges) use unit "%".
- For EPS in rupees, use unit "Rs".
- Shareholding pattern values (promoter / FII / DII / public / pledge) are percentages (0..100).
- Guidance fields: emit `revenue_guidance_lower`/`upper` (and `ebitda_margin_guidance_lower`/`upper`)
  only when management gives an explicit range; if it's a point estimate, set lower = upper = the point.
- Order-book fields are in INR crore unless the document quotes a different unit.
- Negative values use a leading minus, not parentheses.
- `source_text` is `"<raw_label> <formatted_value>"` — never the full multi-column table row.
- Indian quarterly / nine-months results: use ONLY the **Quarter Ended** column for the
  latest quarter (first period column under "Quarter Ended"). NEVER use Nine Months Ended,
  Year Ended, YTD, half-year, or annual cumulative figures.
- When a row shows multiple numbers, take the current quarter ended value only — not prior
  quarter, not prior-year quarter, not nine-month cumulative.
"""


# Max pages we hand to the model. Anthropic allows >20 images only when each is
# ≤2000px and the whole Messages body stays under 32 MB; 20 pages of resized
# JPEGs plus OCR text fits Indian quarterly-result PDFs without 413s.
_MAX_PAGES_TO_SEND = 20

# Anthropic: >20 images per request → 2000px max dimension; Messages API → 32 MB body.
_MAX_LLM_IMAGE_DIMENSION = 2000
_LLM_JPEG_QUALITY = 85

# Cap OCR text per page so transcript PDFs do not blow the request budget.
_MAX_PAGE_TEXT_CHARS = 12_000


def _fit_page_image_for_llm(image_bytes: bytes) -> tuple[bytes, str]:
    """Downscale and JPEG-compress a page PNG for the provider wire format."""
    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes))
    if img.mode != "RGB":
        img = img.convert("RGB")
    w, h = img.size
    longest = max(w, h)
    if longest > _MAX_LLM_IMAGE_DIMENSION:
        scale = _MAX_LLM_IMAGE_DIMENSION / longest
        img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=_LLM_JPEG_QUALITY, optimize=True)
    return buf.getvalue(), "image/jpeg"


def _b64_image(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("ascii")


def _build_anthropic_content_blocks(
    *, pages: list[ProviderPage], document_title: str
) -> list[dict[str, Any]]:
    """Multimodal Anthropic message content: header text + per-page image+text blocks."""
    blocks: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                f"Document title: {document_title}\n"
                f"Total pages: {len(pages)} (sending first {min(len(pages), _MAX_PAGES_TO_SEND)})\n\n"
                "Extract the financial line items by calling the emit_financial_facts tool."
            ),
        }
    ]
    for page in pages[:_MAX_PAGES_TO_SEND]:
        if page.image_bytes:
            jpeg_bytes, media_type = _fit_page_image_for_llm(page.image_bytes)
            blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": _b64_image(jpeg_bytes),
                    },
                }
            )
        ocr = page.text or "(no text)"
        if len(ocr) > _MAX_PAGE_TEXT_CHARS:
            ocr = ocr[:_MAX_PAGE_TEXT_CHARS] + "\n…(truncated)"
        blocks.append(
            {
                "type": "text",
                "text": f"--- PAGE {page.page_number} OCR ---\n{ocr}",
            }
        )
    return blocks


def _build_openai_content_parts(
    *, pages: list[ProviderPage], document_title: str
) -> list[dict[str, Any]]:
    """Multimodal OpenAI user-message parts mirroring the Anthropic layout."""
    parts: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                f"Document title: {document_title}\n"
                f"Total pages: {len(pages)} (sending first {min(len(pages), _MAX_PAGES_TO_SEND)})\n\n"
                "Extract the financial line items as JSON matching the financial_facts schema."
            ),
        }
    ]
    for page in pages[:_MAX_PAGES_TO_SEND]:
        if page.image_bytes:
            jpeg_bytes, media_type = _fit_page_image_for_llm(page.image_bytes)
            parts.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{media_type};base64,{_b64_image(jpeg_bytes)}",
                        "detail": "high",
                    },
                }
            )
        ocr = page.text or "(no text)"
        if len(ocr) > _MAX_PAGE_TEXT_CHARS:
            ocr = ocr[:_MAX_PAGE_TEXT_CHARS] + "\n…(truncated)"
        parts.append(
            {
                "type": "text",
                "text": f"--- PAGE {page.page_number} OCR ---\n{ocr}",
            }
        )
    return parts


# ---------------------------------------------------------------------------
# Response parsing (works for tool_use payloads and json_schema responses)
# ---------------------------------------------------------------------------


def _items_from_payload(
    payload: dict[str, Any]
) -> tuple[list[ExtractedLineItem], float, list[str]]:
    """Turn a schema-validated dict into typed `ExtractedLineItem`s."""
    items: list[ExtractedLineItem] = []
    for entry in payload.get("items", []):
        try:
            raw_label = str(entry.get("raw_label", entry["normalized_code"]))
            value = float(entry["value"])
            unit = str(entry.get("unit", "crore"))
            items.append(
                ExtractedLineItem(
                    normalized_code=str(entry["normalized_code"]).strip(),
                    raw_label=raw_label,
                    value=value,
                    unit=unit,
                    page_number=int(entry["page_number"]) if entry.get("page_number") else None,
                    source_text=_source_quote(raw_label, value, unit),
                    confidence=float(entry.get("confidence", 85.0)),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Skipping malformed item from LLM: %s (%s)", entry, exc)
    overall = float(payload.get("overall_confidence", 85.0))
    notes = list(payload.get("notes", []))
    return items, overall, notes


def parse_extraction_payload(
    raw_response: str,
) -> tuple[list[ExtractedLineItem], float, list[str]]:
    """Public entry point used by the extraction cache replay path."""
    try:
        payload = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        return [], 0.0, [f"Cached LLM payload is not valid JSON: {exc}"]
    return _items_from_payload(payload)


def _finalize_quarter_items(
    items: list[ExtractedLineItem],
    *,
    pages: list[tuple[int, str]],
) -> list[ExtractedLineItem]:
    from app.services.pipeline.quarter_column import enforce_quarter_ended_only

    return enforce_quarter_ended_only(items, pages=pages)


# ---------------------------------------------------------------------------
# Provider: Anthropic Claude (tool use)
# ---------------------------------------------------------------------------


_ANTHROPIC_TOOL = {
    "name": "emit_financial_facts",
    "description": (
        "Emit every financial line item that appears in the document, scoped to "
        "the latest Quarter Ended column. Call this tool exactly once."
    ),
    "input_schema": _EXTRACTION_JSON_SCHEMA,
}


def _anthropic_omit_sampling_params(model: str) -> bool:
    """True when the Messages API rejects ``temperature`` (e.g. Opus 4.7)."""
    return "opus-4-7" in model.lower()


def _anthropic_sampling_temperature(model: str) -> float | None:
    """Requested temperature for bookkeeping; ``None`` when omitted from the API."""
    return None if _anthropic_omit_sampling_params(model) else 0.0


# Anthropic prompt caching. The system prompt + tool schema are byte-identical
# on every extraction call, so marking them as ``ephemeral`` cache breakpoints
# turns the input cost on those blocks from $3/MTok (Sonnet 4.6 input) down to
# $0.30/MTok on cache hits. Cache writes cost 1.25× input — break-even is
# reached after ~2 calls within the 5-minute TTL.
_CACHE_BREAKPOINT: dict[str, str] = {"type": "ephemeral"}


def _cached_anthropic_system(prompt: str) -> list[dict[str, Any]]:
    """System prompt as a single cached text block."""
    return [{"type": "text", "text": prompt, "cache_control": _CACHE_BREAKPOINT}]


def _cached_anthropic_tools(tool: dict[str, Any]) -> list[dict[str, Any]]:
    """Tool list with the cache breakpoint on the last tool entry."""
    return [{**tool, "cache_control": _CACHE_BREAKPOINT}]


# Document types that prefer the cheap-tier model when ``LLM_MODEL_FAST`` is
# set. ``FINANCIAL_RESULT`` always uses ``LLM_MODEL`` so dense Quarter-Ended
# extraction stays on the premium tier.
_FAST_LANE_DOCUMENT_TYPES: frozenset[str] = frozenset(
    {
        "CONCALL_TRANSCRIPT",
        "INVESTOR_PRESENTATION",
        "PRESS_RELEASE",
        "ANNUAL_REPORT",
    }
)


def select_extraction_model(document: Any) -> str:
    """Pick the active LLM_MODEL for ``document.document_type``.

    Returns ``settings.LLM_MODEL_FAST`` for transcript / presentation /
    press-release / annual-report documents when that env var is set,
    otherwise ``settings.LLM_MODEL``.
    """
    fast_model = (settings.LLM_MODEL_FAST or "").strip()
    if not fast_model:
        return settings.LLM_MODEL
    doc_type = getattr(document, "document_type", None)
    type_value = getattr(doc_type, "value", doc_type)
    if type_value in _FAST_LANE_DOCUMENT_TYPES:
        return fast_model
    return settings.LLM_MODEL


class AnthropicProvider:
    """Calls Claude with structured tool use and parses the tool-call payload."""

    name: str

    def __init__(self, model: str, api_key: str, *, seed: int | None = None) -> None:
        # Imported lazily so installs that never set ANTHROPIC_API_KEY don't
        # pay the import cost.
        from anthropic import Anthropic  # type: ignore

        self._client = Anthropic(api_key=api_key)
        self._model = model
        self._seed = seed
        self.name = f"anthropic:{model}"

    def extract_financial_facts(
        self, *, pages: list[ProviderPage], document_title: str
    ) -> ExtractionResult:
        content = _build_anthropic_content_blocks(
            pages=pages, document_title=document_title
        )

        create_kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": 4096,
            "system": _cached_anthropic_system(_EXTRACTION_SYSTEM_PROMPT),
            "tools": _cached_anthropic_tools(_ANTHROPIC_TOOL),
            "tool_choice": {"type": "tool", "name": _ANTHROPIC_TOOL["name"]},
            "messages": [{"role": "user", "content": content}],
        }
        if not _anthropic_omit_sampling_params(self._model):
            create_kwargs["temperature"] = 0
        resp = self._client.messages.create(**create_kwargs)

        tool_payload: dict[str, Any] | None = None
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use" and block.name == _ANTHROPIC_TOOL["name"]:
                tool_payload = dict(block.input or {})
                break

        if tool_payload is None:
            # Model failed to call the tool. Surface as a hard error so the
            # extraction job lands in the Review Queue instead of pretending
            # to succeed with zero items.
            raise RuntimeError(
                "Anthropic response did not include the expected tool_use call "
                f"({_ANTHROPIC_TOOL['name']})."
            )

        raw = json.dumps(tool_payload, sort_keys=True)
        items, overall, notes = _items_from_payload(tool_payload)
        items = _finalize_quarter_items(
            items, pages=[(p.page_number, p.text or "") for p in pages]
        )

        return ExtractionResult(
            items=items,
            model_name=self.name,
            input_tokens=getattr(resp.usage, "input_tokens", None),
            output_tokens=getattr(resp.usage, "output_tokens", None),
            overall_confidence=overall,
            raw_response=raw,
            notes=notes,
            temperature=_anthropic_sampling_temperature(self._model),
            seed=self._seed,
            provider_used="anthropic",
        )


# ---------------------------------------------------------------------------
# Provider: OpenAI (structured output via json_schema strict)
# ---------------------------------------------------------------------------


class OpenAIProvider:
    """Calls OpenAI chat completions with strict JSON-schema response format."""

    name: str

    def __init__(self, model: str, api_key: str, *, seed: int | None = None) -> None:
        from openai import OpenAI  # type: ignore

        self._client = OpenAI(api_key=api_key)
        self._model = model
        self._seed = seed
        self.name = f"openai:{model}"

    def extract_financial_facts(
        self, *, pages: list[ProviderPage], document_title: str
    ) -> ExtractionResult:
        user_parts = _build_openai_content_parts(
            pages=pages, document_title=document_title
        )

        request_kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": 4096,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": _EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": user_parts},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "financial_facts",
                    "strict": True,
                    "schema": _EXTRACTION_JSON_SCHEMA,
                },
            },
        }
        if self._seed is not None:
            request_kwargs["seed"] = self._seed

        resp = self._client.chat.completions.create(**request_kwargs)

        raw = (resp.choices[0].message.content or "").strip()
        if not raw:
            raise RuntimeError("OpenAI response message is empty.")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"OpenAI returned non-JSON payload: {exc}") from exc

        # Re-serialize so the cached `raw_response` is canonical (key order
        # independent of the provider's choice) — keeps the request-hash cache
        # stable across model versions that re-order top-level keys.
        canonical_raw = json.dumps(payload, sort_keys=True)
        items, overall, notes = _items_from_payload(payload)
        items = _finalize_quarter_items(
            items, pages=[(p.page_number, p.text or "") for p in pages]
        )
        usage = resp.usage

        return ExtractionResult(
            items=items,
            model_name=self.name,
            input_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
            output_tokens=getattr(usage, "completion_tokens", None) if usage else None,
            overall_confidence=overall,
            raw_response=canonical_raw,
            notes=notes,
            temperature=0.0,
            seed=self._seed,
            provider_used="openai",
        )


# ---------------------------------------------------------------------------
# RAG answer generation (read-side; uses same provider factory)
# ---------------------------------------------------------------------------


@dataclass
class RAGChunk:
    page_id: int
    document_id: int
    page_number: int
    document_title: str
    text: str


@dataclass
class RAGCitation:
    page_id: int
    document_id: int
    page_number: int
    quote: str


@dataclass
class RAGAnswerResult:
    answer: str
    citations: list[RAGCitation]


_RAG_SYSTEM_PROMPT = """You answer questions about Indian company filings using ONLY the provided passages.
Return strict JSON with this shape:
{
  "answer": "<concise answer in plain English>",
  "citations": [{"page_id": <int>, "quote": "<verbatim excerpt from that passage>"}]
}
Every factual claim must have at least one citation. Use only page_id values from the passages.
If the passages do not contain enough information, say so clearly and return an empty citations array."""


def answer_from_context(*, question: str, chunks: list[RAGChunk]) -> RAGAnswerResult:
    """Generate a cited answer from retrieved document passages."""
    if not chunks:
        return RAGAnswerResult(
            answer="No relevant passages were retrieved for this question.",
            citations=[],
        )

    provider = get_provider()
    if isinstance(provider, MockProvider):
        return _mock_rag_answer(question, chunks)

    user_message = _build_rag_user_message(question=question, chunks=chunks)
    try:
        if isinstance(provider, AnthropicProvider):
            raw = _anthropic_rag_raw(provider, user_message)
        elif isinstance(provider, OpenAIProvider):
            raw = _openai_rag_raw(provider, user_message)
        else:
            return _mock_rag_answer(question, chunks)
    except Exception as exc:
        if settings.is_production:
            raise
        logger.exception("RAG LLM call failed; using mock answer: %s", exc)
        return _mock_rag_answer(question, chunks)

    return _parse_rag_json_response(raw, chunks)


def _build_rag_user_message(*, question: str, chunks: list[RAGChunk]) -> str:
    from app.core.config import settings as cfg

    max_chars = cfg.RAG_MAX_CHUNK_CHARS
    parts: list[str] = []
    for chunk in chunks:
        text = chunk.text[:max_chars]
        parts.append(
            f"--- PASSAGE page_id={chunk.page_id} document_id={chunk.document_id} "
            f"page_number={chunk.page_number} title={chunk.document_title!r} ---\n{text}"
        )
    joined = "\n\n".join(parts)
    return f"Question: {question}\n\nPassages:\n\n{joined}"


def _parse_rag_json_response(raw: str, chunks: list[RAGChunk]) -> RAGAnswerResult:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    m = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not m:
        return _mock_rag_answer("", chunks)
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return _mock_rag_answer("", chunks)

    chunk_by_page = {c.page_id: c for c in chunks}
    citations: list[RAGCitation] = []
    for entry in data.get("citations", []):
        try:
            page_id = int(entry["page_id"])
            quote = str(entry.get("quote", "")).strip()
            if not quote or page_id not in chunk_by_page:
                continue
            chunk = chunk_by_page[page_id]
            citations.append(
                RAGCitation(
                    page_id=page_id,
                    document_id=chunk.document_id,
                    page_number=chunk.page_number,
                    quote=quote,
                )
            )
        except (KeyError, TypeError, ValueError):
            continue

    answer = str(data.get("answer", "")).strip()
    if not answer:
        return _mock_rag_answer("", chunks)
    return RAGAnswerResult(answer=answer, citations=citations)


def _mock_rag_answer(question: str, chunks: list[RAGChunk]) -> RAGAnswerResult:
    del question
    lines: list[str] = []
    citations: list[RAGCitation] = []
    for chunk in chunks[:3]:
        excerpt = chunk.text.strip().replace("\n", " ")
        if len(excerpt) > 220:
            excerpt = excerpt[:217] + "..."
        lines.append(
            f"From {chunk.document_title} (page {chunk.page_number}): {excerpt}"
        )
        quote = chunk.text.strip()[:300]
        citations.append(
            RAGCitation(
                page_id=chunk.page_id,
                document_id=chunk.document_id,
                page_number=chunk.page_number,
                quote=quote,
            )
        )
    answer = " ".join(lines) if lines else "No relevant passages were found."
    return RAGAnswerResult(answer=answer, citations=citations)


def _anthropic_rag_raw(provider: AnthropicProvider, user_message: str) -> str:
    create_kwargs: dict[str, Any] = {
        "model": provider._model,
        "max_tokens": 2048,
        "system": _cached_anthropic_system(_RAG_SYSTEM_PROMPT),
        "messages": [{"role": "user", "content": user_message}],
    }
    if not _anthropic_omit_sampling_params(provider._model):
        create_kwargs["temperature"] = 0
    resp = provider._client.messages.create(**create_kwargs)
    text_chunks = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
    return "".join(text_chunks).strip()


def _openai_rag_raw(provider: OpenAIProvider, user_message: str) -> str:
    resp = provider._client.chat.completions.create(
        model=provider._model,
        max_tokens=2048,
        temperature=0,
        seed=provider._seed,
        messages=[
            {"role": "system", "content": _RAG_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
    )
    return (resp.choices[0].message.content or "").strip()


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------


def get_provider(*, model: str | None = None) -> LLMProvider:
    """Build an `LLMProvider` for the configured `LLM_PROVIDER`.

    Pass ``model`` to override ``settings.LLM_MODEL`` for a single call (used
    by the per-document-type fast lane in `extraction.run_extraction`).
    """
    provider_name = (settings.LLM_PROVIDER or "mock").lower()
    seed = int(getattr(settings, "LLM_SEED", 42))
    chosen_model = model or settings.LLM_MODEL
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
        return AnthropicProvider(model=chosen_model, api_key=api_key, seed=seed)
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
        return OpenAIProvider(model=chosen_model, api_key=api_key, seed=seed)
    if settings.is_production:
        raise RuntimeError(
            "APP_ENV=production cannot use LLM_PROVIDER=mock. "
            "Set LLM_PROVIDER=anthropic or openai with a valid API key."
        )
    return MockProvider()
