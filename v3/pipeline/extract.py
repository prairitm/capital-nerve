"""PDF parse and LLM fact extraction using v2 catalog + logic."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config import settings

_PERIOD_ENDED_DAY_FIRST_RE = re.compile(
    r"period ended\s+(\d{1,2})\s+([A-Za-z]+)\s*,?\s*(\d{4})",
    re.IGNORECASE,
)
_PERIOD_ENDED_MONTH_FIRST_RE = re.compile(
    r"period ended\s+([A-Za-z]+)\s+(\d{1,2})\s*,?\s*(\d{4})",
    re.IGNORECASE,
)
_PERIOD_ENDED_HYPHEN_RE = re.compile(
    r"period ended\s+(\d{1,2})-([A-Za-z]{3,})-(\d{4})",
    re.IGNORECASE,
)


@dataclass
class ExtractionResult:
    markdown: str
    period: Any
    accepted_rows: list[dict[str, Any]]
    rejected_rows: list[dict[str, Any]]


def _openai_client():
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    from openai import OpenAI

    return OpenAI(api_key=settings.openai_api_key)


def parse_pdf_to_markdown(pdf_path: Path, *, force: bool = False) -> str:
    try:
        from capital_nerve_parse import pdf_to_markdown_page_by_page, should_reparse, write_parse_meta
    except ImportError:
        from pdf_parse import parse_pdf_to_markdown as _v2_parse

        return _v2_parse(
            pdf_path,
            parsed_dir=settings.parsed_dir,
            client=_openai_client(),
            model=settings.openai_parse_model,
            force=force,
        )

    settings.parsed_dir.mkdir(parents=True, exist_ok=True)
    md_path = settings.parsed_dir / f"{pdf_path.stem}.md"
    digest = __import__("hashlib").sha256(pdf_path.read_bytes()).hexdigest()

    if not should_reparse(md_path, pdf_path, source_sha256=digest, force=force):
        return md_path.read_text(encoding="utf-8")

    client = _openai_client()
    markdown = pdf_to_markdown_page_by_page(
        pdf_path,
        client=client,
        model=settings.openai_parse_model,
    )
    md_path.write_text(markdown, encoding="utf-8")
    write_parse_meta(
        md_path.with_suffix(".meta.json"),
        source_sha256=digest,
        page_count=markdown.count("\n#") + 1,
    )
    return markdown


def _period_from_announcement_text(text: str) -> Any:
    from datetime import date

    from periods import _month_from_name, reporting_period_from_date

    for pattern, day_first in (
        (_PERIOD_ENDED_HYPHEN_RE, True),
        (_PERIOD_ENDED_DAY_FIRST_RE, True),
        (_PERIOD_ENDED_MONTH_FIRST_RE, False),
    ):
        m = pattern.search(text or "")
        if not m:
            continue
        if day_first:
            day, month_name, year = int(m.group(1)), m.group(2), int(m.group(3))
        else:
            month_name, day, year = m.group(1), int(m.group(2)), int(m.group(3))
        month = _month_from_name(month_name)
        if month:
            return reporting_period_from_date(date(year, month, day), "announcement_text")
    return None


def detect_period(markdown: str, title: str = "") -> Any:
    from periods import detect_reporting_period

    period = detect_reporting_period(markdown, title=title)
    if period:
        return period

    period = _period_from_announcement_text(title)
    if period:
        return period

    return detect_reporting_period(markdown[:12000], title=title)


def _chunk_markdown(markdown: str, *, max_chars: int = 12000) -> list[str]:
    if len(markdown) <= max_chars:
        return [markdown]
    chunks: list[str] = []
    start = 0
    while start < len(markdown):
        end = min(len(markdown), start + max_chars)
        if end < len(markdown):
            break_at = markdown.rfind("\n\n", start, end)
            if break_at > start:
                end = break_at
        chunks.append(markdown[start:end])
        start = end
    return chunks


def _extraction_schema() -> dict[str, Any]:
    from catalog_loader import allowed_extraction_keys, get_catalog

    catalog = get_catalog()
    fact_keys = allowed_extraction_keys()
    fact_lines = []
    for key, spec in catalog.facts.items():
        aliases = ", ".join(spec.get("aliases") or [])
        alias_note = f" (aliases: {aliases})" if aliases else ""
        fact_lines.append(f"- {key}: {spec.get('name')} [{spec.get('unit')}]{alias_note}")

    return {
        "fact_keys": fact_keys,
        "fact_catalog_text": "\n".join(fact_lines),
    }


def _extract_facts_from_chunk(
    client: Any,
    chunk: str,
    *,
    period_label: str,
    schema_info: dict[str, Any],
) -> list[dict[str, Any]]:
    prompt = f"""Extract financial facts from this Indian corporate filing markdown.

Reporting period context: {period_label}

Allowed fact_key values (use canonical keys from catalog):
{schema_info['fact_catalog_text']}

Rules:
- Extract ONLY values explicitly present in the markdown for the current quarter column
- Prefer consolidated over standalone when both appear
- basis must be "consolidated" or "standalone"
- numeric_value must be a number (strip commas)
- unit should match catalog (crore, Rs, etc.)
- evidence: short verbatim snippet containing the number
- confidence: 0.0 to 1.0

Return JSON object: {{"facts": [{{"fact_key": "...", "numeric_value": 0.0, "unit": "...", "period": "...", "basis": "consolidated", "evidence": "...", "confidence": 0.9}}]}}
If no facts found, return {{"facts": []}}.

Markdown:
{chunk}
"""
    response = client.responses.create(
        model=settings.openai_model,
        input=[{"role": "user", "content": prompt}],
        text={"format": {"type": "json_object"}},
        temperature=0,
    )
    raw = (response.output_text or "").strip()
    payload = json.loads(raw)
    facts = payload.get("facts") or []
    if not isinstance(facts, list):
        return []
    return [f for f in facts if isinstance(f, dict)]


def extract_facts(
    markdown: str,
    *,
    period: Any,
    document_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        from capital_nerve_logic import (
            accept_for_preferred_basis,
            canonicalize_unit,
            dedupe_eps_values,
            is_blocking_check,
            validation_checks,
        )
        from catalog_loader import canonical_fact_key, get_catalog
    except ImportError:
        from catalog_loader import canonical_fact_key, get_catalog

        def canonicalize_unit(unit):  # type: ignore[misc]
            if not unit:
                return None
            u = str(unit).strip().lower()
            return {"crores": "crore", "cr": "crore", "rs.": "Rs", "rs": "Rs"}.get(u, unit)

        def validation_checks(row, _basis):  # type: ignore[misc]
            return []

        def is_blocking_check(_check):  # type: ignore[misc]
            return False

        def dedupe_eps_values(rows, **_kw):  # type: ignore[misc]
            return rows

        def accept_for_preferred_basis(rows, preferred, **_kw):  # type: ignore[misc]
            by_key: dict[str, dict[str, Any]] = {}
            for row in rows:
                fk = row.get("fact_key") or row.get("value_code")
                basis = (row.get("basis") or "consolidated").lower()
                cur = by_key.get(fk)
                if cur is None or (basis == preferred and cur.get("basis") != preferred):
                    by_key[fk] = row
            return list(by_key.values())

    from quarter_column import extract_facts_from_quarter_column

    schema_info = _extraction_schema()
    client = _openai_client()
    period_label = period.label if period else ""

    catalog = get_catalog()
    det_by_key = {
        row["fact_key"]: row
        for row in extract_facts_from_quarter_column(
            markdown,
            target=period,
            fact_keys=set(catalog.facts.keys()),
            facts_catalog=catalog.facts,
        )
    }

    raw_facts: list[dict[str, Any]] = [
        {
            "fact_key": row["fact_key"],
            "numeric_value": row["numeric_value"],
            "unit": row.get("unit"),
            "basis": row.get("basis") or "consolidated",
            "evidence": row.get("evidence") or "",
            "confidence": row.get("confidence") or 0.92,
            "period": period_label,
        }
        for row in det_by_key.values()
    ]
    missing_keys = set(catalog.facts.keys()) - set(det_by_key)

    for chunk in _chunk_markdown(markdown):
        for entry in _extract_facts_from_chunk(
            client, chunk, period_label=period_label, schema_info=schema_info
        ):
            fk = entry.get("fact_key")
            canonical = canonical_fact_key(str(fk)) if fk else None
            if canonical and canonical in det_by_key:
                continue
            if canonical and canonical not in missing_keys:
                continue
            raw_facts.append(entry)

    validated: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for entry in raw_facts:
        fact_key = entry.get("fact_key")
        if not fact_key:
            continue
        canonical = canonical_fact_key(str(fact_key)) or str(fact_key)
        try:
            numeric = float(str(entry.get("numeric_value", "")).replace(",", ""))
        except (TypeError, ValueError):
            rejected.append({**entry, "status": "rejected", "checks": ["non_numeric"]})
            continue

        row = {
            "fact_key": canonical,
            "value_code": canonical,
            "numeric_value": numeric,
            "unit": canonicalize_unit(entry.get("unit")),
            "basis": (entry.get("basis") or "consolidated").strip().lower(),
            "evidence": entry.get("evidence") or "",
            "source_text": entry.get("evidence") or "",
            "source_page": entry.get("source_page"),
            "confidence": float(entry.get("confidence") or 0.7),
            "period": entry.get("period") or period_label,
            "document_id": document_id,
            "status": "accepted",
        }
        checks = validation_checks(row, "consolidated")
        blocking = [c for c in checks if is_blocking_check(c)]
        if blocking:
            row["status"] = "rejected"
            row["checks"] = checks
            rejected.append(row)
        else:
            row["checks"] = checks
            validated.append(row)

    validated = dedupe_eps_values(
        validated,
        fact_key=lambda r: r["fact_key"],
        evidence=lambda r: r.get("evidence") or "",
        period=lambda r: r.get("period"),
        basis=lambda r: r.get("basis"),
        document_id=lambda r: r.get("document_id") or document_id,
    )

    accepted = accept_for_preferred_basis(
        validated,
        "consolidated",
        status=lambda r: r["status"],
        basis=lambda r: r.get("basis"),
    )
    accepted_ids = {id(r) for r in accepted}
    for r in validated:
        if id(r) not in accepted_ids and r["status"] == "accepted":
            r["status"] = "rejected"
            r["checks"] = (r.get("checks") or []) + ["basis_filtered"]
            rejected.append(r)

    return accepted, rejected


def run_extraction(
    pdf_path: Path,
    *,
    title: str = "",
    document_id: str,
    force: bool = False,
) -> ExtractionResult:
    markdown = parse_pdf_to_markdown(pdf_path, force=force)
    period = detect_period(markdown, title=title)
    if not period:
        raise RuntimeError("Could not detect reporting period from PDF or title")

    accepted, rejected = extract_facts(
        markdown, period=period, document_id=document_id
    )
    if not accepted:
        raise RuntimeError("No facts passed validation after extraction")

    return ExtractionResult(
        markdown=markdown,
        period=period,
        accepted_rows=accepted,
        rejected_rows=rejected,
    )
