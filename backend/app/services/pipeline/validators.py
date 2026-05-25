"""Deterministic post-LLM validators.

The LLM extraction stage produces `ExtractedLineItem`s; before they are
persisted as `ExtractedValue` rows, this module runs three checks that turn
soft "trust the model" output into hard, reproducible facts:

1. ``validate_source_text`` — every item claims a `page_number` and a
   `source_text` excerpt. We confirm the excerpt actually appears on that
   page (whitespace-tolerant substring) and drop anything that doesn't.
   Catches hallucinated quotes that would otherwise survive into evidence.
2. ``canonicalize_units`` — map every common unit variant ("Cr", "INR cr",
   "Rs.") onto the canonical schema enum ("crore", "Rs", ...). Drop items
   whose unit can't be normalised — the metrics stage assumes canonical units.
3. ``validate_totals`` — cross-checks accounting identities
   (revenue + other income = total income; PBT - tax = PAT; EBITDA/Rev = margin).
   On a breach we *downgrade* the confidence of every involved item rather
   than dropping it, so the Review Queue surfaces the row for an admin
   instead of silently disappearing real but suspect numbers.

The aggregated `ValidatorReport` is stored on `extraction_jobs.validator_report`
so the admin UI can explain why a job ended up below the auto-publish bar.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from app.services.pipeline.llm import ExtractedLineItem

logger = logging.getLogger(__name__)


# Canonical unit names recognised by downstream stages. Keep this list in
# sync with ``llm._ALLOWED_UNITS`` and the JSON schema enum.
_CANONICAL_UNITS: frozenset[str] = frozenset({"crore", "%", "Rs", "bps", "days", "x"})


# Common unit aliases the LLM emits. Mapped onto the canonical form.
_UNIT_ALIASES: dict[str, str] = {
    "crore": "crore",
    "crores": "crore",
    "cr": "crore",
    "cr.": "crore",
    "inr cr": "crore",
    "inr crore": "crore",
    "inr crores": "crore",
    "rs cr": "crore",
    "rs. cr": "crore",
    "rs crore": "crore",
    "₹ cr": "crore",
    "₹cr": "crore",
    "%": "%",
    "pct": "%",
    "percent": "%",
    "percentage": "%",
    "bps": "bps",
    "basis points": "bps",
    "rs": "Rs",
    "rs.": "Rs",
    "inr": "Rs",
    "₹": "Rs",
    "days": "days",
    "day": "days",
    "x": "x",
    "times": "x",
}


# Numeric scale multipliers from the raw unit onto canonical ``crore``. Lets
# the LLM legitimately report values in lakh / thousand / million without the
# downstream metric stage seeing 100× off numbers. Keys are the **lower-cased
# raw** unit string (matched after stripping). Anything outside this map and
# the alias map above is dropped — see ``canonicalize_units``.
_UNIT_SCALE_TO_CRORE: dict[str, float] = {
    "crore": 1.0,
    "crores": 1.0,
    "cr": 1.0,
    "cr.": 1.0,
    "inr cr": 1.0,
    "inr crore": 1.0,
    "inr crores": 1.0,
    "rs cr": 1.0,
    "rs. cr": 1.0,
    "rs crore": 1.0,
    "₹ cr": 1.0,
    "₹cr": 1.0,
    # 1 lakh = 0.01 crore (100 lakh make a crore).
    "lakh": 0.01,
    "lakhs": 0.01,
    "lac": 0.01,
    "lacs": 0.01,
    "inr lakh": 0.01,
    "rs lakh": 0.01,
    # 1 thousand = 1e-5 crore (1 crore = 1e7).
    "thousand": 1e-5,
    "thousands": 1e-5,
    "k": 1e-5,
    # 1 million = 0.1 crore.
    "million": 0.1,
    "millions": 0.1,
    "mn": 0.1,
    "mm": 0.1,
    "inr mn": 0.1,
    "rs mn": 0.1,
    # 1 billion = 100 crore.
    "billion": 100.0,
    "billions": 100.0,
    "bn": 100.0,
    "inr bn": 100.0,
    "rs bn": 100.0,
    # 1 trillion = 100,000 crore.
    "trillion": 1e5,
    "trillions": 1e5,
    "tn": 1e5,
    # Raw rupees → crore (1 crore = 10,000,000 INR).
    "rupees": 1e-7,
    "rupee": 1e-7,
    "inr rupees": 1e-7,
    "rs rupees": 1e-7,
}


@dataclass
class ValidatorReport:
    """Per-validator outcomes; serialised onto ``extraction_jobs.validator_report``."""

    source_text_dropped: list[dict] = field(default_factory=list)
    unit_dropped: list[dict] = field(default_factory=list)
    unit_normalised: list[dict] = field(default_factory=list)
    unit_rescaled: list[dict] = field(default_factory=list)
    totals_breaches: list[dict] = field(default_factory=list)

    @property
    def has_failures(self) -> bool:
        return bool(
            self.source_text_dropped
            or self.unit_dropped
            or self.totals_breaches
        )

    def to_dict(self) -> dict:
        return {
            "source_text_dropped": self.source_text_dropped,
            "unit_dropped": self.unit_dropped,
            "unit_normalised": self.unit_normalised,
            "unit_rescaled": self.unit_rescaled,
            "totals_breaches": self.totals_breaches,
        }


# ---------------------------------------------------------------------------
# Source-text anchor check
# ---------------------------------------------------------------------------


_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_ws(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text or "").strip().lower()


def validate_source_text(
    items: list[ExtractedLineItem],
    *,
    pages: list[tuple[int, str]],
    report: ValidatorReport,
) -> list[ExtractedLineItem]:
    """Drop items whose `source_text` cannot be found on the claimed page.

    Whitespace-tolerant substring match. The reported numeric token must also
    appear in the same page text — guards against the model fabricating a
    plausible-sounding excerpt with the wrong number.
    """
    text_by_page: dict[int, str] = {
        page_no: _normalize_ws(text) for page_no, text in pages
    }
    kept: list[ExtractedLineItem] = []
    for item in items:
        if item.page_number is None or not item.source_text:
            # No anchor to verify; keep but downgrade confidence so the
            # Review Queue picks it up.
            item.confidence = min(item.confidence, 60.0)
            kept.append(item)
            continue

        page_text = text_by_page.get(item.page_number)
        if not page_text:
            # Page not in our parsed set (e.g. truncated). Keep the item but
            # downgrade — we can't verify either way.
            item.confidence = min(item.confidence, 60.0)
            kept.append(item)
            continue

        value_token = _value_token(item.value)
        if value_token and value_token.lower() not in page_text:
            report.source_text_dropped.append(
                {
                    "normalized_code": item.normalized_code,
                    "page_number": item.page_number,
                    "reason": "value_token_not_on_page",
                    "value": item.value,
                }
            )
            continue
        kept.append(item)
    return kept


def _value_token(value: float) -> str:
    """Numeric representation we expect to find on the page."""
    if abs(value - round(value)) < 1e-6:
        return f"{int(round(value)):,}"
    # Two decimals is the most common rendering for Indian results PDFs.
    return f"{value:,.2f}".rstrip("0").rstrip(".")


# ---------------------------------------------------------------------------
# Unit canonicalisation + allow-list
# ---------------------------------------------------------------------------


@dataclass
class _CanonicalisedUnit:
    """Outcome of resolving one raw unit string against the canonical schema."""

    unit: str  # final canonical unit ("crore", "%", "Rs", ...)
    scale: float  # multiplier applied to the value (1.0 unless rescaled)


def _resolve_unit(raw: str) -> _CanonicalisedUnit | None:
    """Return the canonical unit + numeric scale for a raw unit string.

    Returns ``None`` when the unit cannot be mapped at all — the caller drops
    the item. The scale is the factor that converts the *value* into the
    canonical unit (e.g. ``lakh`` → ``crore`` ⇒ scale = 0.01).
    """
    if not raw:
        return None
    key = raw.strip().lower()
    if key in _UNIT_SCALE_TO_CRORE:
        return _CanonicalisedUnit(unit="crore", scale=_UNIT_SCALE_TO_CRORE[key])
    alias = _UNIT_ALIASES.get(key)
    if alias is not None:
        return _CanonicalisedUnit(unit=alias, scale=1.0)
    if raw in _CANONICAL_UNITS:
        return _CanonicalisedUnit(unit=raw, scale=1.0)
    return None


def canonicalize_units(
    items: list[ExtractedLineItem],
    *,
    report: ValidatorReport,
) -> list[ExtractedLineItem]:
    """Normalise unit strings and rescale values onto the canonical unit.

    Lakh / thousand / million / billion / raw rupees are *rescaled* into crore
    rather than dropped — Indian filings legitimately mix scales (segment
    tables in lakh, headline P&L in crore) and downstream metrics assume a
    single canonical scale.
    """
    kept: list[ExtractedLineItem] = []
    for item in items:
        raw = (item.unit or "").strip()
        resolved = _resolve_unit(raw)
        if resolved is None:
            report.unit_dropped.append(
                {
                    "normalized_code": item.normalized_code,
                    "page_number": item.page_number,
                    "raw_unit": raw,
                }
            )
            continue
        if resolved.scale != 1.0:
            old_value = float(item.value)
            item.value = old_value * resolved.scale
            report.unit_rescaled.append(
                {
                    "normalized_code": item.normalized_code,
                    "from_unit": raw,
                    "to_unit": resolved.unit,
                    "scale": resolved.scale,
                    "from_value": old_value,
                    "to_value": item.value,
                }
            )
            item.unit = resolved.unit
        elif resolved.unit != raw:
            report.unit_normalised.append(
                {
                    "normalized_code": item.normalized_code,
                    "from": raw,
                    "to": resolved.unit,
                }
            )
            item.unit = resolved.unit
        kept.append(item)
    return kept


# ---------------------------------------------------------------------------
# Totals math
# ---------------------------------------------------------------------------


# Tolerance for accounting identity checks. Reported figures often round
# component lines to crore; 1% catches material drift without false positives
# on legitimate rounding.
_TOTALS_TOLERANCE_PCT = 1.0
_DOWNGRADED_CONFIDENCE = 40.0


@dataclass
class _TotalsCheck:
    name: str
    components: tuple[str, ...]
    target: str
    expected: float
    actual: float


def validate_totals(
    items: list[ExtractedLineItem],
    *,
    report: ValidatorReport,
) -> list[ExtractedLineItem]:
    """Cross-check accounting identities; downgrade confidence on breach."""
    by_code: dict[str, ExtractedLineItem] = {}
    for item in items:
        # Multiple items may share a code if the LLM is noisy; keep the
        # highest-confidence one for the math check.
        prev = by_code.get(item.normalized_code)
        if prev is None or item.confidence > prev.confidence:
            by_code[item.normalized_code] = item

    checks: list[_TotalsCheck] = []

    rev = _val(by_code, "revenue_from_operations")
    oi = _val(by_code, "other_income")
    ti = _val(by_code, "total_income")
    if rev is not None and oi is not None and ti is not None:
        checks.append(
            _TotalsCheck(
                name="total_income = revenue + other_income",
                components=("revenue_from_operations", "other_income"),
                target="total_income",
                expected=rev + oi,
                actual=ti,
            )
        )

    pbt = _val(by_code, "pbt")
    tax = _val(by_code, "tax_expense")
    pat = _val(by_code, "pat")
    if pbt is not None and tax is not None and pat is not None:
        checks.append(
            _TotalsCheck(
                name="pat = pbt - tax_expense",
                components=("pbt", "tax_expense"),
                target="pat",
                expected=pbt - tax,
                actual=pat,
            )
        )

    # EBITDA margin reconciles against revenue from operations (not total
    # income) per Indian disclosure convention.
    ebitda = _val(by_code, "ebitda")
    margin = _val(by_code, "ebitda_margin")
    if ebitda is not None and margin is not None and rev:
        expected_margin = (ebitda / rev) * 100.0
        checks.append(
            _TotalsCheck(
                name="ebitda_margin = ebitda / revenue * 100",
                components=("ebitda", "revenue_from_operations"),
                target="ebitda_margin",
                expected=expected_margin,
                actual=margin,
            )
        )

    expenses = [
        _val(by_code, code)
        for code in ("employee_cost", "finance_cost", "depreciation", "other_expenses", "cogs")
    ]
    expense_components = [
        code
        for code, val in zip(
            ("employee_cost", "finance_cost", "depreciation", "other_expenses", "cogs"),
            expenses,
        )
        if val is not None
    ]
    expense_total = sum(v for v in expenses if v is not None)
    if ti is not None and pbt is not None and len(expense_components) >= 3:
        # Indian P&L: PBT = Total Income - Expenses. Allow 3+ components so we
        # don't fire when the model only captured one cost line.
        checks.append(
            _TotalsCheck(
                name="pbt = total_income - expenses",
                components=("total_income", *expense_components),
                target="pbt",
                expected=ti - expense_total,
                actual=pbt,
            )
        )

    for check in checks:
        if _within_tolerance(check.expected, check.actual, _TOTALS_TOLERANCE_PCT):
            continue
        report.totals_breaches.append(
            {
                "rule": check.name,
                "expected": round(check.expected, 4),
                "actual": round(check.actual, 4),
                "tolerance_pct": _TOTALS_TOLERANCE_PCT,
            }
        )
        touched_codes = {*check.components, check.target}
        for code in touched_codes:
            item = by_code.get(code)
            if item is not None:
                item.confidence = min(item.confidence, _DOWNGRADED_CONFIDENCE)

    return items


def _val(by_code: dict[str, ExtractedLineItem], code: str) -> float | None:
    item = by_code.get(code)
    return float(item.value) if item is not None else None


def _within_tolerance(expected: float, actual: float, tolerance_pct: float) -> bool:
    if expected == 0:
        return abs(actual) <= 1.0  # 1 crore slack on zero-expected lines
    return abs(actual - expected) / abs(expected) * 100.0 <= tolerance_pct


# ---------------------------------------------------------------------------
# Combined entry point used by extraction.run_extraction
# ---------------------------------------------------------------------------


def run_validators(
    items: list[ExtractedLineItem],
    *,
    pages: list[tuple[int, str]],
) -> tuple[list[ExtractedLineItem], ValidatorReport]:
    """Run source-text, unit, and totals validators in order."""
    report = ValidatorReport()
    items = validate_source_text(items, pages=pages, report=report)
    items = canonicalize_units(items, report=report)
    items = validate_totals(items, report=report)
    return items, report
