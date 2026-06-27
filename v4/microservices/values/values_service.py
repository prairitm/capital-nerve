"""Value extraction from financial_result_flow.ipynb Step 4."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any

from periods import (
    detect_reporting_period,
    fy_start_year_from_date,
    quarter_end_date,
    quarter_from_date,
    reporting_period_from_date,
)
from pdf_parse import parse_pdf_to_markdown
from quarter_column import extract_facts_from_quarter_column
from values_config import settings
from values_db import bootstrap_schema


def company_id_for_symbol(symbol: str) -> str:
    return hashlib.sha256(f"{symbol}:NSE".encode()).hexdigest()


def value_id(company_id: str, value_code: str, period_end: str, basis: str) -> str:
    return hashlib.sha256(f"{company_id}:{value_code}:{period_end}:{basis}".encode()).hexdigest()


def load_env_value(key: str) -> str:
    if not settings.env_path.exists():
        return ""
    for line in settings.env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return ""


def _event_context(conn: sqlite3.Connection, event_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    return dict(row) if row is not None else {}


def _document_title(event_row: dict[str, Any], fallback_url: str) -> str:
    return str(event_row.get("title") or Path(fallback_url).name or "")


def store_document(
    conn: sqlite3.Connection,
    *,
    company_id: str,
    event_id: str,
    pdf_url: str,
    pdf_bytes: bytes,
    title: str,
) -> dict[str, Any]:
    document_id = hashlib.sha256(pdf_bytes).hexdigest()
    storage_path = settings.documents_dir / f"{document_id}.pdf"
    if not storage_path.exists():
        storage_path.write_bytes(pdf_bytes)

    conn.execute(
        """
        INSERT OR IGNORE INTO documents (
            id, company_id, source_url, storage_path, sha256, title,
            document_kind, file_size, status
        ) VALUES (?, ?, ?, ?, ?, ?, 'FINANCIAL_RESULT', ?, 'ingested')
        """,
        (
            document_id,
            company_id,
            pdf_url,
            str(storage_path),
            document_id,
            title,
            len(pdf_bytes),
        ),
    )
    conn.execute("UPDATE events SET document_id = ? WHERE id = ?", (document_id, event_id))
    conn.commit()
    return {"document_id": document_id, "storage_path": storage_path}


def detect_period(markdown: str, *, title: str, event_row: dict[str, Any]):
    reporting_period = detect_reporting_period(markdown, title=title)
    if reporting_period is not None:
        return reporting_period

    raw_date = str(event_row.get("event_date") or "")
    if not raw_date:
        raise RuntimeError("Could not detect reporting period and event_date is missing")
    ann = date.fromisoformat(raw_date[:10])
    fy = fy_start_year_from_date(ann)
    quarter = quarter_from_date(ann)
    return reporting_period_from_date(quarter_end_date(quarter, fy), "announcement_fallback")


def load_facts_catalog() -> dict[str, Any]:
    return json.loads((settings.catalog_dir / "facts.json").read_text(encoding="utf-8"))


def _chunk(text: str, max_chars: int = 12000) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    chunks, start = [], 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        if end < len(text):
            brk = text.rfind("\n\n", start, end)
            if brk > start:
                end = brk
        chunks.append(text[start:end])
        start = end
    return chunks


def _canon_unit(unit: Any) -> Any:
    if not unit:
        return None
    normalized = str(unit).strip().lower()
    return {"crores": "crore", "cr": "crore", "rs.": "Rs", "rs": "Rs"}.get(
        normalized,
        unit,
    )


def _catalog_aliases(facts_catalog: dict[str, Any]) -> tuple[dict[str, str], str]:
    storage_to_fact: dict[str, str] = {}
    fact_lines: list[str] = []
    for key, spec in facts_catalog.items():
        storage_to_fact[key] = key
        for alias in spec.get("aliases") or []:
            storage_to_fact[str(alias)] = key
        aliases = ", ".join(spec.get("aliases") or [])
        alias_note = f" (aliases: {aliases})" if aliases else ""
        fact_lines.append(f"- {key}: {spec.get('name')} [{spec.get('unit')}]{alias_note}")
    return storage_to_fact, "\n".join(fact_lines)


def extract_facts_from_chunk(
    client: Any,
    *,
    model: str,
    chunk: str,
    period_label: str,
    fact_catalog_text: str,
) -> list[dict[str, Any]]:
    prompt = f"""Extract financial facts from this Indian corporate filing markdown.

Reporting period context: {period_label}

Allowed fact_key values (use canonical keys from catalog):
{fact_catalog_text}

Rules:
- Extract ONLY values explicitly present in the markdown for the current quarter column
- Prefer consolidated over standalone when both appear
- basis must be "consolidated" or "standalone"
- numeric_value must be a number (strip commas)
- unit should match catalog (crore, Rs, etc.)
- evidence: short verbatim snippet containing the number
- confidence: 0.0 to 1.0

Return JSON object: {{"facts": [{{"fact_key": "...", "numeric_value": 0.0, "unit": "...", "basis": "consolidated", "evidence": "...", "confidence": 0.9}}]}}
If no facts found, return {{"facts": []}}.

Markdown:
{chunk}
"""
    response = client.responses.create(
        model=model,
        input=[{"role": "user", "content": prompt}],
        text={"format": {"type": "json_object"}},
        temperature=0,
    )
    payload = json.loads((response.output_text or "{}").strip())
    facts = payload.get("facts") or []
    return [fact for fact in facts if isinstance(fact, dict)]


def canonicalize_facts(
    raw_facts: list[dict[str, Any]],
    *,
    facts_catalog: dict[str, Any],
    storage_to_fact: dict[str, str],
) -> list[dict[str, Any]]:
    cleaned: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in raw_facts:
        fact_key = entry.get("fact_key")
        if not fact_key:
            continue
        canonical = storage_to_fact.get(str(fact_key), str(fact_key))
        if canonical not in facts_catalog:
            continue
        try:
            numeric = float(str(entry.get("numeric_value", "")).replace(",", ""))
        except (TypeError, ValueError):
            continue
        basis = (entry.get("basis") or "consolidated").strip().lower()
        confidence = float(entry.get("confidence") or 0.7)
        row = {
            "fact_key": canonical,
            "numeric_value": numeric,
            "unit": _canon_unit(entry.get("unit")) or facts_catalog[canonical].get("unit"),
            "basis": basis,
            "evidence": entry.get("evidence") or "",
            "confidence": confidence,
        }
        key = (canonical, basis)
        if key not in cleaned or confidence > cleaned[key]["confidence"]:
            cleaned[key] = row

    preferred: dict[str, dict[str, Any]] = {}
    for (fact_key, basis), row in cleaned.items():
        current = preferred.get(fact_key)
        if current is None or (basis == "consolidated" and current["basis"] != "consolidated"):
            preferred[fact_key] = row
    return list(preferred.values())


def persist_extracted_values(
    conn: sqlite3.Connection,
    *,
    company_id: str,
    event_id: str,
    document_id: str,
    period_quarter: int,
    period_fy_start: int,
    period_end: str,
    rows: list[dict[str, Any]],
) -> None:
    for row in rows:
        vid = value_id(company_id, row["fact_key"], period_end, row["basis"])
        conn.execute(
            """
            INSERT INTO extracted_values (
                id, company_id, event_id, value_code, value_numeric, unit,
                period_type, period_start, period_end, basis, source_text, confidence
            ) VALUES (?, ?, ?, ?, ?, ?, 'quarter', NULL, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                event_id = excluded.event_id,
                value_numeric = excluded.value_numeric,
                unit = excluded.unit,
                source_text = excluded.source_text,
                confidence = excluded.confidence
            """,
            (
                vid,
                company_id,
                event_id,
                row["fact_key"],
                row["numeric_value"],
                row["unit"],
                period_end,
                row["basis"],
                row["evidence"],
                row["confidence"],
            ),
        )
    conn.execute(
        "UPDATE events SET status = 'processed', fiscal_year = ?, fiscal_quarter = ? WHERE id = ?",
        (period_fy_start, period_quarter, event_id),
    )
    conn.execute("UPDATE documents SET status = 'processed' WHERE id = ?", (document_id,))
    conn.commit()


def extract_and_persist_values(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    company_id: str,
    event_id: str,
    pdf_url: str,
    pdf_bytes: bytes,
    force_reparse: bool = False,
) -> dict[str, Any]:
    expected_company_id = company_id_for_symbol(symbol)
    if company_id != expected_company_id:
        raise ValueError("company_id does not match the NSE symbol-derived company id")

    bootstrap_schema(conn)
    event_row = _event_context(conn, event_id)
    title = _document_title(event_row, pdf_url)
    stored_doc = store_document(
        conn,
        company_id=company_id,
        event_id=event_id,
        pdf_url=pdf_url,
        pdf_bytes=pdf_bytes,
        title=title,
    )

    openai_api_key = load_env_value("OPENAI_API_KEY")
    openai_model = load_env_value("OPENAI_MODEL") or "gpt-4.1-mini"
    openai_parse_model = load_env_value("OPENAI_PARSE_MODEL") or openai_model
    if not openai_api_key:
        raise RuntimeError(f"OPENAI_API_KEY not found in {settings.env_path}")

    from openai import OpenAI

    client = OpenAI(api_key=openai_api_key)
    markdown = parse_pdf_to_markdown(
        stored_doc["storage_path"],
        parsed_dir=settings.parsed_dir,
        client=client,
        model=openai_parse_model,
        force=force_reparse,
    )

    reporting_period = detect_period(markdown, title=title, event_row=event_row)
    period_end = reporting_period.quarter_end

    facts_catalog = load_facts_catalog()
    storage_to_fact, fact_catalog_text = _catalog_aliases(facts_catalog)
    deterministic_facts = extract_facts_from_quarter_column(
        markdown,
        target=reporting_period,
        fact_keys=set(facts_catalog.keys()),
        facts_catalog=facts_catalog,
    )
    deterministic_by_key = {row["fact_key"]: row for row in deterministic_facts}
    raw_facts: list[dict[str, Any]] = list(deterministic_facts)
    missing_keys = set(facts_catalog.keys()) - set(deterministic_by_key)

    for chunk in _chunk(markdown):
        for entry in extract_facts_from_chunk(
            client,
            model=openai_model,
            chunk=chunk,
            period_label=reporting_period.label,
            fact_catalog_text=fact_catalog_text,
        ):
            fact_key = entry.get("fact_key")
            canonical = storage_to_fact.get(str(fact_key), str(fact_key)) if fact_key else None
            if canonical and canonical in deterministic_by_key:
                continue
            if canonical and canonical not in missing_keys:
                continue
            raw_facts.append(entry)

    accepted_rows = canonicalize_facts(
        raw_facts,
        facts_catalog=facts_catalog,
        storage_to_fact=storage_to_fact,
    )
    if not accepted_rows:
        raise RuntimeError("No facts passed validation after extraction")

    persist_extracted_values(
        conn,
        company_id=company_id,
        event_id=event_id,
        document_id=stored_doc["document_id"],
        period_quarter=reporting_period.quarter,
        period_fy_start=reporting_period.fy_start_year,
        period_end=period_end,
        rows=accepted_rows,
    )

    return {
        "document_id": stored_doc["document_id"],
        "storage_path": str(stored_doc["storage_path"]),
        "markdown_length": len(markdown),
        "reporting_period": reporting_period.to_dict(),
        "values": accepted_rows,
    }
