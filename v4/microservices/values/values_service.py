"""Value extraction from financial_result_flow.ipynb Step 4."""

from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import logging
import re
import sqlite3
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Callable

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

logger = logging.getLogger("uvicorn.error")

_NEWSPAPER_MARKERS = re.compile(
    r"\b(?:newspaper|financial\s+express|business\s+standard|economic\s+times|epaper)\b",
    re.IGNORECASE,
)
_ISSUER_HEADING = re.compile(
    r"^#{1,6}\s+(.{2,120}?\b(?:limited|ltd\.?)\b)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_NON_ISSUER_HEADINGS = {
    "national stock exchange of india limited",
    "bse limited",
}
_PAGE_MARKER_RE = re.compile(r"^# Page (\d+)\s*$", re.MULTILINE)


def company_id_for_symbol(symbol: str) -> str:
    return hashlib.sha256(f"{symbol}:NSE".encode()).hexdigest()


def is_multi_issuer_newspaper(markdown: str) -> bool:
    """Return true when a filing is a newspaper page carrying several issuers.

    Such pages are unsafe for automatic extraction because visual parsers can
    associate a neighbouring issuer's table with the target issuer's heading.
    """
    if not _NEWSPAPER_MARKERS.search(markdown):
        return False
    issuers = {
        re.sub(r"\s+", " ", match.group(1)).strip().lower().rstrip(".")
        for match in _ISSUER_HEADING.finditer(markdown)
    }
    issuers.difference_update(_NON_ISSUER_HEADINGS)
    return len(issuers) >= 2


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


_EVENT_SUMMARY_RESPONSE_FORMAT = {
    "type": "json_schema",
    "name": "event_summary",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "headline": {"type": "string"},
            "summary": {"type": "string"},
            "key_points": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 3,
                "maxItems": 3,
            },
            "investor_takeaway": {"type": "string"},
        },
        "required": ["headline", "summary", "key_points", "investor_takeaway"],
        "additionalProperties": False,
    },
}


def _summary_markdown(markdown: str, max_chars: int = 400_000) -> str:
    if len(markdown) <= max_chars:
        return markdown
    leading_chars = int(max_chars * 0.6)
    trailing_chars = max_chars - leading_chars
    return (
        markdown[:leading_chars]
        + "\n\n[Middle of long document omitted for summary cost control]\n\n"
        + markdown[-trailing_chars:]
    )


def generate_event_summary(
    client: Any,
    *,
    model: str,
    markdown: str,
    company_name: str,
    event_title: str,
    event_type: str,
) -> dict[str, Any]:
    prompt = f"""Create a high-impact professional investor summary of this Indian corporate filing.

Company: {company_name}
Event type: {event_type}
Filing title: {event_title}

Requirements:
- Use only information explicitly present in the markdown. Never invent, extrapolate, or add outside knowledge.
- Prioritize material financial performance, operational change, management decisions, guidance, risks, and catalysts.
- Make the headline specific and decisive, not promotional, with at most 14 words.
- Use neutral, professional wording; avoid promotional or emotive verbs such as "sparks", "soars", or "plunges".
- Write a concise 2-3 sentence executive summary that explains what changed and why it matters.
- Return exactly 3 key points. Use concrete figures when the filing provides them.
- Read the unit printed above each table and preserve every number in that exact unit. For example,
  if a table is labelled "INR crore", 20,211 means INR 20,211 crore, never INR 20.21 crore.
- Write one professional investor takeaway describing the central implication, not investment advice.
- Keep reporting periods exactly as written in the filing; do not invent or shorten a fiscal-year label.
- Do not speculate about tax, impairment, valuation, or future revenue mix unless the filing explicitly does so.
- In the takeaway, connect only reported facts. Do not assert a transaction's accounting or
  consolidated impact unless the filing explicitly states it.
- Avoid filler such as "the company announced" when a more direct statement is possible.
- Preserve uncertainty and qualifiers from the filing.

Filing markdown:
{_summary_markdown(markdown)}
"""
    request_options: dict[str, Any] = {
        "model": model,
        "input": [{"role": "user", "content": prompt}],
        "text": {"format": _EVENT_SUMMARY_RESPONSE_FORMAT},
        "max_output_tokens": 1_500,
    }
    if model.startswith("gpt-5"):
        request_options["reasoning"] = {"effort": "minimal"}
    response = client.responses.create(
        **request_options,
    )
    payload = json.loads((response.output_text or "{}").strip())
    headline = str(payload.get("headline") or "").strip()
    summary = str(payload.get("summary") or "").strip()
    key_points = [
        str(point).strip()
        for point in (payload.get("key_points") or [])
        if str(point).strip()
    ][:3]
    investor_takeaway = str(payload.get("investor_takeaway") or "").strip()
    if not headline or not summary or len(key_points) != 3 or not investor_takeaway:
        raise RuntimeError("OpenAI returned an incomplete event summary")
    return {
        "headline": headline,
        "summary": summary,
        "key_points": key_points,
        "investor_takeaway": investor_takeaway,
    }


def generate_event_summary_for_event(
    conn: sqlite3.Connection,
    *,
    client: Any,
    model: str,
    event_id: str,
    force: bool = False,
) -> dict[str, Any]:
    bootstrap_schema(conn)
    event = conn.execute(
        "SELECT * FROM events WHERE id = ?", (event_id,)
    ).fetchone()
    if event is None:
        raise LookupError("Event not found")
    document_id = str(event["document_id"] or "")
    if not document_id:
        raise RuntimeError("Event has no source document")
    document = conn.execute(
        "SELECT * FROM documents WHERE id = ?", (document_id,)
    ).fetchone()
    if document is None:
        raise RuntimeError("Source document not found")
    markdown_path = settings.parsed_dir / f"{document_id}.md"
    if not markdown_path.exists():
        raise RuntimeError("Parsed markdown is not available for this event")
    markdown = markdown_path.read_text(encoding="utf-8")
    markdown_sha256 = hashlib.sha256(markdown.encode("utf-8")).hexdigest()

    if not force:
        cached = conn.execute(
            """
            SELECT * FROM event_summaries
            WHERE event_id = ? AND markdown_sha256 = ? AND model = ?
            """,
            (event_id, markdown_sha256, model),
        ).fetchone()
        if cached is not None:
            return {
                "event_id": event_id,
                "document_id": document_id,
                "model": cached["model"],
                "headline": cached["headline"],
                "summary": cached["summary"],
                "key_points": json.loads(cached["key_points_json"]),
                "investor_takeaway": cached["investor_takeaway"],
                "generated_at": cached["updated_at"],
                "cached": True,
            }

    company = conn.execute(
        "SELECT name FROM companies WHERE id = ?", (event["company_id"],)
    ).fetchone()
    generated = generate_event_summary(
        client,
        model=model,
        markdown=markdown,
        company_name=str(company["name"] if company is not None else "Unknown company"),
        event_title=str(event["title"] or document["title"] or "Corporate filing"),
        event_type=str(event["event_type"] or document["document_kind"] or "Corporate filing"),
    )
    now = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    conn.execute(
        """
        INSERT INTO event_summaries (
            event_id, document_id, markdown_sha256, model, headline, summary,
            key_points_json, investor_takeaway, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(event_id) DO UPDATE SET
            document_id = excluded.document_id,
            markdown_sha256 = excluded.markdown_sha256,
            model = excluded.model,
            headline = excluded.headline,
            summary = excluded.summary,
            key_points_json = excluded.key_points_json,
            investor_takeaway = excluded.investor_takeaway,
            updated_at = excluded.updated_at
        """,
        (
            event_id,
            document_id,
            markdown_sha256,
            model,
            generated["headline"],
            generated["summary"],
            json.dumps(generated["key_points"], ensure_ascii=False),
            generated["investor_takeaway"],
            now,
            now,
        ),
    )
    conn.commit()
    return {
        "event_id": event_id,
        "document_id": document_id,
        "model": model,
        **generated,
        "generated_at": now,
        "cached": False,
    }


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
    document_kind: str = "FINANCIAL_RESULT",
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
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ingested')
        """,
        (
            document_id,
            company_id,
            pdf_url,
            str(storage_path),
            document_id,
            title,
            document_kind,
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


def load_presentation_facts_catalog() -> dict[str, Any]:
    path = settings.catalog_dir / "investor_presentation_facts.json"
    if not path.exists():
        path = settings.catalog_dir / "investor_presentation" / "presentation_facts.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_earnings_call_facts_catalog() -> dict[str, Any]:
    path = settings.catalog_dir / "earnings_call_facts.json"
    if not path.exists():
        path = settings.catalog_dir / "earnings-call" / "earnings_call_facts.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _fact_value_type(spec: dict[str, Any]) -> str:
    fact_type = str(spec.get("fact_type") or "").lower()
    unit = str(spec.get("unit") or "").lower()
    if fact_type in {"text", "categorical", "date"} or unit in {"text", "date", "enum"}:
        return "text"
    return "numeric"


def _preferred_source(spec: dict[str, Any], fallback: str) -> str:
    docs = spec.get("documents") or []
    return str(docs[0] if docs else fallback).lower()


def seed_fact_definitions(
    conn: sqlite3.Connection,
    *,
    facts_catalog: dict[str, Any],
    preferred_source: str,
) -> None:
    for code, spec in facts_catalog.items():
        unit = spec.get("unit")
        standard_unit = "INR crore" if unit == "crore" else unit
        conn.execute(
            """
            INSERT INTO fact_definitions (
                fact_code, fact_name, fact_category, value_type,
                standard_unit, preferred_source
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(fact_code) DO UPDATE SET
                fact_name = excluded.fact_name,
                fact_category = excluded.fact_category,
                value_type = excluded.value_type,
                standard_unit = excluded.standard_unit,
                preferred_source = excluded.preferred_source
            """,
            (
                code,
                spec.get("name", code),
                str(spec.get("statement") or "financial").lower(),
                _fact_value_type(spec),
                standard_unit,
                _preferred_source(spec, preferred_source),
            ),
        )


def _observation_id(
    company_id: str,
    event_id: str,
    document_id: str,
    row: dict[str, Any],
    period_end: str,
) -> str:
    parts = [
        company_id,
        event_id,
        document_id,
        row["fact_key"],
        period_end,
        row.get("basis") or "",
        row.get("segment") or "",
        row.get("geography") or "",
        row.get("product") or "",
        row.get("channel") or "",
        row.get("project") or "",
        row.get("customer_type") or "",
        row.get("metric_context") or "",
        row.get("scope_level") or "",
        row.get("scope_name") or "",
        row.get("value_text") or "",
        row.get("evidence") or "",
    ]
    return hashlib.sha256(":".join(parts).encode()).hexdigest()


def _resolved_fact_id(company_id: str, event_id: str, fact_key: str) -> str:
    return hashlib.sha256(f"{company_id}:{event_id}:{fact_key}".encode()).hexdigest()


def _resolved_fact_id_for_row(company_id: str, event_id: str, row: dict[str, Any]) -> str:
    dims = ":".join(
        str(row.get(key) or "")
        for key in (
            "segment",
            "geography",
            "product",
            "channel",
            "project",
            "customer_type",
            "metric_context",
            "scope_level",
            "scope_name",
        )
    )
    identity = ":".join(
        (
            company_id,
            event_id,
            row["fact_key"],
            str(row.get("period_end") or ""),
            str(row.get("period_type") or ""),
            str(row.get("basis") or ""),
            dims,
        )
    )
    return hashlib.sha256(identity.encode()).hexdigest()


def _best_key(row: dict[str, Any], period_end: str) -> tuple[Any, ...]:
    return (
        row["fact_key"],
        row.get("period_end") or period_end,
        row.get("period_type"),
        row.get("basis") or "consolidated",
        row.get("segment"),
        row.get("geography"),
        row.get("product"),
        row.get("channel"),
        row.get("project"),
        row.get("customer_type"),
        row.get("metric_context"),
        row.get("scope_level"),
        row.get("scope_name"),
    )


def persist_fact_observations_and_resolutions(
    conn: sqlite3.Connection,
    *,
    company_id: str,
    event_id: str,
    document_id: str,
    period_end: str,
    rows: list[dict[str, Any]],
) -> None:
    best_by_fact: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        numeric_value = row.get("numeric_value")
        value_text = row.get("value_text")
        if numeric_value is None and value_text is None:
            continue
        oid = _observation_id(company_id, event_id, document_id, row, period_end)
        source_text = row.get("source_text") or row.get("evidence") or ""
        conn.execute(
            """
            INSERT INTO fact_observations (
                observation_id, company_id, event_id, document_id, fact_code,
                value, value_text, unit, period, period_type, basis,
                source_page, source_text,
                segment, geography, product, channel, project, customer_type,
                metric_context, scope_level, scope_name, fact_type,
                extraction_method, value_lower, value_upper, sentiment,
                is_explicit_guidance, confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(observation_id) DO UPDATE SET
                value = excluded.value,
                value_text = excluded.value_text,
                unit = excluded.unit,
                period = excluded.period,
                period_type = excluded.period_type,
                basis = excluded.basis,
                source_page = excluded.source_page,
                source_text = excluded.source_text,
                segment = excluded.segment,
                geography = excluded.geography,
                product = excluded.product,
                channel = excluded.channel,
                project = excluded.project,
                customer_type = excluded.customer_type,
                metric_context = excluded.metric_context,
                scope_level = excluded.scope_level,
                scope_name = excluded.scope_name,
                fact_type = excluded.fact_type,
                extraction_method = excluded.extraction_method,
                value_lower = excluded.value_lower,
                value_upper = excluded.value_upper,
                sentiment = excluded.sentiment,
                is_explicit_guidance = excluded.is_explicit_guidance,
                confidence = excluded.confidence
            """,
            (
                oid,
                company_id,
                event_id,
                document_id,
                row["fact_key"],
                numeric_value,
                value_text,
                row.get("unit"),
                row.get("period_end") or period_end,
                row.get("period_type"),
                row.get("basis") or "consolidated",
                row.get("source_page"),
                source_text,
                row.get("segment"),
                row.get("geography"),
                row.get("product"),
                row.get("channel"),
                row.get("project"),
                row.get("customer_type"),
                row.get("metric_context"),
                row.get("scope_level"),
                row.get("scope_name"),
                row.get("fact_type"),
                row.get("extraction_method"),
                row.get("value_lower"),
                row.get("value_upper"),
                row.get("sentiment"),
                row.get("is_explicit_guidance"),
                row.get("confidence"),
            ),
        )
        candidate = {**row, "observation_id": oid}
        best_key = _best_key(row, period_end)
        current = best_by_fact.get(best_key)
        if current is None:
            best_by_fact[best_key] = candidate
            continue
        current_basis = current.get("basis")
        row_basis = row.get("basis")
        if row_basis == "consolidated" and current_basis != "consolidated":
            best_by_fact[best_key] = candidate
            continue
        if (row.get("confidence") or 0) > (current.get("confidence") or 0):
            best_by_fact[best_key] = candidate

    for _, row in best_by_fact.items():
        resolution_status = (
            "review_required"
            if row.get("has_unresolved_conflict")
            or row.get("decision") in {"review", "abstain"}
            else "resolved"
        )
        conn.execute(
            """
            INSERT INTO resolved_facts (
                resolved_fact_id, company_id, event_id, fact_code,
                resolved_value, resolved_value_text, unit, period, period_type, basis,
                segment, geography, product, channel, project, customer_type,
                metric_context, scope_level, scope_name, fact_type,
                value_lower, value_upper, sentiment, is_explicit_guidance,
                selected_observation_id, resolution_status, confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(resolved_fact_id) DO UPDATE SET
                resolved_value = excluded.resolved_value,
                resolved_value_text = excluded.resolved_value_text,
                unit = excluded.unit,
                period = excluded.period,
                period_type = excluded.period_type,
                basis = excluded.basis,
                segment = excluded.segment,
                geography = excluded.geography,
                product = excluded.product,
                channel = excluded.channel,
                project = excluded.project,
                customer_type = excluded.customer_type,
                metric_context = excluded.metric_context,
                scope_level = excluded.scope_level,
                scope_name = excluded.scope_name,
                fact_type = excluded.fact_type,
                value_lower = excluded.value_lower,
                value_upper = excluded.value_upper,
                sentiment = excluded.sentiment,
                is_explicit_guidance = excluded.is_explicit_guidance,
                selected_observation_id = excluded.selected_observation_id,
                resolution_status = excluded.resolution_status,
                confidence = excluded.confidence
            """,
            (
                _resolved_fact_id_for_row(company_id, event_id, row),
                company_id,
                event_id,
                row["fact_key"],
                row.get("numeric_value"),
                row.get("value_text"),
                row.get("unit"),
                row.get("period_end") or period_end,
                row.get("period_type"),
                row.get("basis") or "consolidated",
                row.get("segment"),
                row.get("geography"),
                row.get("product"),
                row.get("channel"),
                row.get("project"),
                row.get("customer_type"),
                row.get("metric_context"),
                row.get("scope_level"),
                row.get("scope_name"),
                row.get("fact_type"),
                row.get("value_lower"),
                row.get("value_upper"),
                row.get("sentiment"),
                row.get("is_explicit_guidance"),
                row["observation_id"],
                resolution_status,
                row.get("confidence"),
            ),
        )


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


def _marked_page_numbers(markdown: str) -> set[int]:
    return {int(match.group(1)) for match in _PAGE_MARKER_RE.finditer(markdown)}


def _chunk_financial_markdown(markdown: str, max_chars: int = 12000) -> list[str]:
    """Chunk financial-result markdown without separating content from its page marker."""
    markers = list(_PAGE_MARKER_RE.finditer(markdown))
    if not markers:
        return _chunk(markdown, max_chars=max_chars)

    page_blocks: list[str] = []
    for index, marker in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(markdown)
        block = markdown[marker.start():end].strip()
        if len(block) <= max_chars:
            page_blocks.append(block)
            continue

        header = marker.group(0)
        body = block[len(header):].lstrip()
        body_limit = max(max_chars - len(header) - 2, 1)
        page_blocks.extend(
            f"{header}\n\n{part}" for part in _chunk(body, max_chars=body_limit)
        )

    separator = "\n\n---\n\n"
    chunks: list[str] = []
    current = ""
    for block in page_blocks:
        candidate = f"{current}{separator}{block}" if current else block
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = block
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _validate_fact_source_pages(
    facts: list[dict[str, Any]], chunk: str
) -> list[dict[str, Any]]:
    """Keep only page citations that reference a page marker in the supplied chunk."""
    allowed_pages = _marked_page_numbers(chunk)
    validated: list[dict[str, Any]] = []
    for fact in facts:
        item = dict(fact)
        source_page = _optional_positive_int(item.get("source_page"))
        item["source_page"] = source_page if source_page in allowed_pages else None
        validated.append(item)
    return validated


def _canon_unit(unit: Any) -> Any:
    if not unit:
        return None
    normalized = str(unit).strip().lower()
    return {"crores": "crore", "cr": "crore", "rs.": "Rs", "rs": "Rs"}.get(
        normalized,
        unit,
    )


def _canon_presentation_unit(unit: Any) -> Any:
    if not unit:
        return None
    normalized = str(unit).strip().lower()
    return {
        "crores": "crore",
        "cr": "crore",
        "rs.": "Rs",
        "rs": "Rs",
        "percent": "%",
        "pct": "%",
        "percentage": "%",
    }.get(normalized, unit)


def _clean_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _optional_bool(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return 1 if value else 0
    text = str(value).strip().lower()
    if text in {"true", "yes", "1"}:
        return 1
    if text in {"false", "no", "0"}:
        return 0
    return None


def _optional_positive_int(value: Any) -> int | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _slug(value: Any) -> str | None:
    text = _clean_str(value)
    if not text:
        return None
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug or text.lower()


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


_FINANCIAL_FACTS_RESPONSE_FORMAT = {
    "type": "json_schema",
    "name": "financial_facts",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "facts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "fact_key": {"type": "string"},
                        "numeric_value": {"type": "number"},
                        "unit": {"type": "string"},
                        "basis": {
                            "type": "string",
                            "enum": ["consolidated", "standalone"],
                        },
                        "source_page": {"type": "integer", "minimum": 1},
                        "evidence": {"type": "string"},
                        "confidence": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 1,
                        },
                    },
                    "required": [
                        "fact_key",
                        "numeric_value",
                        "unit",
                        "basis",
                        "source_page",
                        "evidence",
                        "confidence",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["facts"],
        "additionalProperties": False,
    },
}


def extract_facts_from_chunk(
    client: Any,
    *,
    model: str,
    chunk: str,
    symbol: str,
    company_name: str,
    period_label: str,
    period_end: str,
    fact_catalog_text: str,
) -> list[dict[str, Any]]:
    marked_pages = sorted(_marked_page_numbers(chunk))
    marked_page_text = ", ".join(str(page) for page in marked_pages) or "none"
    period_end_dmy = ""
    try:
        parsed_period_end = date.fromisoformat(period_end)
        period_end_dmy = parsed_period_end.strftime("%d.%m.%Y")
    except ValueError:
        period_end_dmy = period_end
    prompt = f"""Extract financial facts from this Indian corporate filing markdown.

Target company: {company_name} (NSE symbol: {symbol})
Reporting period context: {period_label}
Target quarter-end date: {period_end} ({period_end_dmy})

Allowed fact_key values (use canonical keys from catalog):
{fact_catalog_text}

Rules:
- Extract facts ONLY for the target company named above
- Ignore tables, advertisements, or results belonging to any other issuer
- Extract ONLY values explicitly present in the markdown for the current quarter column
- First identify the table column for the current quarter (usually labelled "Quarter ended" or "3 Months ended")
- The target column must contain the target quarter-end date above
- Do NOT extract from "Twelve Months ended", "Year ended", "Nine Months ended", "Corresponding", or "Preceding" columns
- Prefer consolidated over standalone when both appear
- basis must be "consolidated" or "standalone"
- numeric_value must be a number (strip commas)
- unit should match catalog (crore, Rs, etc.)
- evidence: short verbatim snippet containing the number
- source_page is required and must be the number from the # Page heading that contains the evidence
- Page numbers available in this chunk: {marked_page_text}
- Never invent a page number or cite a page outside the available page numbers
- confidence: 0.0 to 1.0

Return JSON object: {{"facts": [{{"fact_key": "...", "numeric_value": 0.0, "unit": "...", "basis": "consolidated", "source_page": 1, "evidence": "...", "confidence": 0.9}}]}}
If no facts found, return {{"facts": []}}.

Markdown:
{chunk}
"""
    response = client.responses.create(
        model=model,
        input=[{"role": "user", "content": prompt}],
        text={"format": _FINANCIAL_FACTS_RESPONSE_FORMAT},
        temperature=0,
    )
    payload = json.loads((response.output_text or "{}").strip())
    facts = payload.get("facts") or []
    return _validate_fact_source_pages(
        [fact for fact in facts if isinstance(fact, dict)], chunk
    )


def _presentation_catalog_aliases(facts_catalog: dict[str, Any]) -> tuple[dict[str, str], str]:
    storage_to_fact: dict[str, str] = {}
    fact_lines: list[str] = []
    for key, spec in facts_catalog.items():
        storage_to_fact[key] = key
        for alias in spec.get("aliases") or []:
            storage_to_fact[str(alias)] = key
        aliases = ", ".join(spec.get("aliases") or [])
        dimensions = ", ".join(spec.get("dimensions") or [])
        allowed = ", ".join(spec.get("allowed_values") or [])
        fact_type = spec.get("fact_type") or "NUMERIC"
        notes = []
        if aliases:
            notes.append(f"aliases: {aliases}")
        if dimensions:
            notes.append(f"dimensions: {dimensions}")
        if allowed:
            notes.append(f"allowed_values: {allowed}")
        note = f" ({'; '.join(notes)})" if notes else ""
        fact_lines.append(
            f"- {key}: {spec.get('name')} [{spec.get('unit')}; {fact_type}; {spec.get('statement')}]{note}"
        )
    return storage_to_fact, "\n".join(fact_lines)


def extract_presentation_facts_from_chunk(
    client: Any,
    *,
    model: str,
    chunk: str,
    symbol: str,
    period_label: str,
    period_end: str,
    fact_catalog_text: str,
) -> list[dict[str, Any]]:
    prompt = f"""Extract investor-presentation facts from this Indian company presentation markdown.

Document type: INVESTOR_PRESENTATION
Company: {symbol}
Reporting period context: {period_label} (quarter_end={period_end})

Allowed fact_key values (use only canonical keys from this catalog):
{fact_catalog_text}

Extraction rules:
- Extract ONLY values explicitly stated in the markdown. Do not calculate, infer, annualize, or fill missing values.
- This is a presentation, not a statutory financial-results table. Look for slide KPIs, charts, segment/product/geography tables, order book/inflow, capacity, utilization, capex, projects, debt/cash, guidance, and management outlook.
- Prefer values for the current/latest reported period. Also extract forward-looking guidance, planned capacity additions, and expected commissioning dates when the slide explicitly labels them.
- Preserve business dimensions when present: segment, product, geography, project, plant, fiscal_year, and period_label.
- For NUMERIC facts, set numeric_value to a number with commas stripped and text_value to null.
- For DATE facts, set text_value to the exact date/quarter/month label and numeric_value to null.
- For CATEGORICAL facts, set text_value to one allowed catalog value exactly and numeric_value to null.
- unit should be the exact reported unit when possible; use catalog units like crore, %, count, date, enum, company_reported, or currency_per_unit when the slide unit is generic.
- basis should be "presentation" unless the slide explicitly says consolidated or standalone.
- evidence must be a short snippet containing the value and its label.
- confidence must be between 0.0 and 1.0.

Return JSON object only:
{{"facts": [{{"fact_key": "...", "numeric_value": 0.0, "text_value": null, "unit": "...", "basis": "presentation", "segment": null, "product": null, "geography": null, "project": null, "plant": null, "fiscal_year": null, "period_label": "...", "evidence": "...", "confidence": 0.9}}]}}
If no catalog facts are present, return {{"facts": []}}.

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


def extract_unified_document_facts_from_chunk(
    client: Any,
    *,
    model: str,
    chunk: str,
    symbol: str,
    document_type: str,
    period_label: str,
    period_end: str,
    fact_catalog_text: str,
) -> list[dict[str, Any]]:
    prompt = f"""Extract facts from this Indian company document markdown/text.

Document type: {document_type}
Company: {symbol}
Reporting period context: {period_label} (quarter_end={period_end})

Allowed fact_key values (use only canonical keys from this catalog):
{fact_catalog_text}

Rules:
- Extract ONLY values explicitly stated in the text. Do not infer missing values.
- Preserve dimensions when present: segment, product, geography, channel, project, customer_type, metric_context.
- Every fact should include scope_level = company|segment|geography|product|channel|project|customer_type|unknown and scope_name when applicable.
- For numeric facts, set numeric_value to a number with commas stripped.
- For dates/categorical/text facts, set value_text to the exact concise value and numeric_value to null.
- Use value_lower/value_upper for guidance ranges and numeric_value as midpoint when both bounds exist.
- Include sentiment only when clear: positive|neutral|mixed|negative.
- evidence must be a short snippet containing the value and label.
- confidence must be between 0.0 and 1.0.

Return JSON object only:
{{"facts": [{{"fact_key": "...", "fact_type": "financial_metric|operational_metric|guidance|strategic_update|market_claim|risk_or_caveat", "numeric_value": 0.0, "value_lower": null, "value_upper": null, "value_text": null, "unit": "...", "period_label": "...", "period_end": "YYYY-MM-DD", "basis": "consolidated|standalone|presentation|not_applicable", "scope": {{"level": "segment", "name": "..."}}, "segment": null, "geography": null, "product": null, "channel": null, "project": null, "customer_type": null, "metric_context": null, "sentiment": null, "is_explicit_guidance": false, "source_page": 1, "evidence": "...", "confidence": 0.9}}]}}
If no catalog facts are present, return {{"facts": []}}.

Document text:
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
    candidates: dict[tuple[str, str, str | None], list[dict[str, Any]]] = {}
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
            "source_text": entry.get("source_text") or entry.get("evidence") or "",
            "source_page": _optional_positive_int(entry.get("source_page")),
            "period_end": _clean_str(entry.get("period_end")),
            "period_type": _clean_str(entry.get("period_type")) or "quarter",
            "extraction_method": _clean_str(entry.get("extraction_method")) or "unknown",
            "upstream_decision": _clean_str(entry.get("decision")),
            "upstream_conflict": bool(entry.get("has_unresolved_conflict")),
            "conflict_reason": _clean_str(entry.get("conflict_reason")),
            "confidence": confidence,
        }
        key = (canonical, basis, row["period_end"])
        candidates.setdefault(key, []).append(row)

    cleaned: list[dict[str, Any]] = []
    for rows in candidates.values():
        ranked = sorted(rows, key=lambda row: row["confidence"], reverse=True)
        selected = dict(ranked[0])
        comparable = [
            row
            for row in ranked[1:]
            if selected["confidence"] - row["confidence"] <= 0.05
        ]
        conflicts = [
            row
            for row in comparable
            if abs(selected["numeric_value"] - row["numeric_value"]) > 0.01
        ]
        if any(row.get("upstream_conflict") for row in ranked):
            selected["decision"] = "review"
            selected["evidence_status"] = "conflicting"
            selected["has_unresolved_conflict"] = True
            selected["conflict_reason"] = next(
                (
                    row.get("conflict_reason")
                    for row in ranked
                    if row.get("conflict_reason")
                ),
                "upstream_extraction_conflict",
            )
        elif conflicts:
            all_conflicts = [selected, *conflicts]
            selected["decision"] = "review"
            selected["evidence_status"] = "conflicting"
            selected["has_unresolved_conflict"] = True
            selected["conflict_count"] = len(all_conflicts)
            selected["conflict_values"] = sorted(
                {row["numeric_value"] for row in all_conflicts}
            )
            selected["conflict_source_pages"] = sorted(
                {
                    row["source_page"]
                    for row in all_conflicts
                    if row.get("source_page") is not None
                }
            )
        elif not selected.get("source_page") and not selected.get("source_text", "").strip():
            selected["decision"] = "abstain"
            selected["evidence_status"] = "missing"
            selected["has_unresolved_conflict"] = False
        elif not selected.get("source_page") or not selected.get("source_text", "").strip():
            selected["decision"] = "review"
            selected["evidence_status"] = "incomplete"
            selected["has_unresolved_conflict"] = False
        else:
            selected["decision"] = "publish"
            selected["evidence_status"] = "complete"
            selected["has_unresolved_conflict"] = False
        cleaned.append(selected)

    return cleaned


def _dimension_payload(entry: dict[str, Any]) -> dict[str, str]:
    dims: dict[str, str] = {}
    for key in (
        "segment",
        "product",
        "geography",
        "channel",
        "project",
        "customer_type",
        "metric_context",
        "plant",
        "fiscal_year",
        "period_label",
    ):
        value = _clean_str(entry.get(key))
        if value:
            dims[key] = _slug(value) if key != "period_label" else value
    return dims


def _primary_segment(dims: dict[str, str]) -> str | None:
    return (
        dims.get("segment")
        or dims.get("product")
        or dims.get("project")
        or dims.get("plant")
        or dims.get("fiscal_year")
    )


def _scope_payload(entry: dict[str, Any], dims: dict[str, str]) -> tuple[str | None, str | None]:
    scope = entry.get("scope")
    if isinstance(scope, dict):
        level = _slug(scope.get("level")) or "unknown"
        name = _slug(scope.get("name"))
    else:
        level = _slug(entry.get("scope_level")) or None
        name = _slug(entry.get("scope_name")) or None
    if not level:
        for key in ("segment", "geography", "product", "channel", "project", "customer_type"):
            if dims.get(key):
                return key, dims[key]
        return "company", None
    if level in {"segment", "geography", "product", "channel", "project", "customer_type"} and not name:
        name = dims.get(level)
    return level, name


def _source_text(evidence: str, dims: dict[str, str]) -> str:
    if not dims:
        return evidence
    dim_text = ", ".join(f"{key}={value}" for key, value in dims.items())
    return f"{evidence} | dimensions: {dim_text}" if evidence else f"dimensions: {dim_text}"


def canonicalize_presentation_facts(
    raw_facts: list[dict[str, Any]],
    *,
    facts_catalog: dict[str, Any],
    storage_to_fact: dict[str, str],
) -> list[dict[str, Any]]:
    cleaned: dict[tuple[Any, ...], dict[str, Any]] = {}
    for entry in raw_facts:
        fact_key = entry.get("fact_key")
        if not fact_key:
            continue
        canonical = storage_to_fact.get(str(fact_key), str(fact_key))
        spec = facts_catalog.get(canonical)
        if spec is None:
            continue

        fact_type = str(spec.get("fact_type") or "NUMERIC").upper()
        raw_value = entry.get("numeric_value", entry.get("value"))
        value_text = _clean_str(entry.get("text_value") or entry.get("value_text") or entry.get("value"))
        numeric_value = None
        if fact_type == "NUMERIC":
            try:
                numeric_value = float(str(raw_value).replace(",", ""))
            except (TypeError, ValueError):
                lower = _optional_float(entry.get("value_lower") or entry.get("lower_value"))
                upper = _optional_float(entry.get("value_upper") or entry.get("upper_value"))
                if lower is not None and upper is not None:
                    numeric_value = (lower + upper) / 2.0
                else:
                    continue
        elif fact_type == "DATE":
            if not value_text:
                value_text = _clean_str(entry.get("numeric_value"))
            if not value_text:
                continue
        elif fact_type == "CATEGORICAL":
            if not value_text:
                continue
            allowed = {str(value).upper() for value in spec.get("allowed_values") or []}
            value_text = value_text.strip().upper()
            if allowed and value_text not in allowed:
                continue
        else:
            if value_text is None and entry.get("numeric_value") is not None:
                value_text = _clean_str(entry.get("numeric_value"))
            if value_text is None:
                continue

        basis = (entry.get("basis") or "presentation").strip().lower()
        confidence = float(entry.get("confidence") or 0.7)
        dims = _dimension_payload(entry)
        scope_level, scope_name = _scope_payload(entry, dims)
        evidence = _clean_str(entry.get("evidence")) or ""
        row = {
            "fact_key": canonical,
            "numeric_value": numeric_value,
            "value_text": value_text,
            "unit": _canon_presentation_unit(entry.get("unit")) or spec.get("unit"),
            "basis": basis,
            "segment": _primary_segment(dims),
            "geography": dims.get("geography"),
            "product": dims.get("product"),
            "channel": dims.get("channel"),
            "project": dims.get("project"),
            "customer_type": dims.get("customer_type"),
            "metric_context": dims.get("metric_context"),
            "scope_level": scope_level,
            "scope_name": scope_name,
            "fact_type": str(entry.get("fact_type") or spec.get("fact_type") or fact_type).lower(),
            "value_lower": _optional_float(entry.get("value_lower") or entry.get("lower_value")),
            "value_upper": _optional_float(entry.get("value_upper") or entry.get("upper_value")),
            "sentiment": _slug(entry.get("sentiment")),
            "is_explicit_guidance": _optional_bool(entry.get("is_explicit_guidance")),
            "source_page": entry.get("source_page"),
            "dimensions": dims,
            "period_label": dims.get("period_label"),
            "period_end": entry.get("period_end"),
            "evidence": evidence,
            "source_text": _source_text(evidence, dims),
            "confidence": confidence,
            "extraction_method": "llm",
        }
        key = (
            canonical,
            basis,
            row["segment"],
            row["geography"],
            row["product"],
            row["channel"],
            row["project"],
            row["customer_type"],
            row["metric_context"],
            row["scope_level"],
            row["scope_name"],
            row["period_label"],
            value_text if fact_type != "NUMERIC" else None,
        )
        if key not in cleaned or confidence > cleaned[key]["confidence"]:
            cleaned[key] = row
    return list(cleaned.values())


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
    facts_catalog: dict[str, Any],
) -> None:
    seed_fact_definitions(
        conn,
        facts_catalog=facts_catalog,
        preferred_source="financial_result",
    )
    for row in rows:
        if row.get("decision") in {"review", "abstain"} or row.get("has_unresolved_conflict"):
            continue
        vid = value_id(company_id, row["fact_key"], period_end, row["basis"])
        conn.execute(
            """
            INSERT INTO extracted_values (
                id, company_id, event_id, value_code, value_numeric, unit,
                period_type, period_start, period_end, basis, source_text,
                source_page, confidence
            ) VALUES (?, ?, ?, ?, ?, ?, 'quarter', NULL, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                event_id = excluded.event_id,
                value_numeric = excluded.value_numeric,
                unit = excluded.unit,
                source_text = excluded.source_text,
                source_page = excluded.source_page,
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
                row.get("source_text") or row["evidence"],
                row.get("source_page"),
                row["confidence"],
            ),
        )
    persist_fact_observations_and_resolutions(
        conn,
        company_id=company_id,
        event_id=event_id,
        document_id=document_id,
        period_end=period_end,
        rows=rows,
    )
    conn.execute(
        "UPDATE events SET status = 'processed', fiscal_year = ?, fiscal_quarter = ? WHERE id = ?",
        (period_fy_start, period_quarter, event_id),
    )
    conn.execute("UPDATE documents SET status = 'processed' WHERE id = ?", (document_id,))
    conn.commit()


def presentation_value_id(
    company_id: str,
    row: dict[str, Any],
    period_end: str,
) -> str:
    parts = [
        company_id,
        row["fact_key"],
        period_end,
        row["basis"],
        row.get("segment") or "",
        row.get("geography") or "",
        row.get("product") or "",
        row.get("channel") or "",
        row.get("project") or "",
        row.get("customer_type") or "",
        row.get("metric_context") or "",
        row.get("scope_level") or "",
        row.get("scope_name") or "",
        row.get("period_label") or "",
        row.get("value_text") or "",
    ]
    return hashlib.sha256(":".join(parts).encode()).hexdigest()


def persist_presentation_inventory(
    conn: sqlite3.Connection,
    *,
    company_id: str,
    event_id: str,
    document_id: str,
    period_label: str,
    rows: list[dict[str, Any]],
) -> None:
    segments: dict[str, dict[str, Any]] = {}
    slide_plan: list[dict[str, Any]] = []
    for row in rows:
        scope_level = row.get("scope_level") or "unknown"
        scope_name = row.get("scope_name") or row.get("segment")
        source_page = row.get("source_page")
        if scope_name:
            segment = segments.setdefault(
                scope_name,
                {
                    "segment_name": scope_name,
                    "aliases": sorted({scope_name}),
                    "slides": set(),
                    "confidence": 0.0,
                },
            )
            if source_page:
                segment["slides"].add(source_page)
            segment["confidence"] = max(segment["confidence"], float(row.get("confidence") or 0.0))
        slide_plan.append(
            {
                "slide_no": source_page,
                "primary_scope_level": scope_level,
                "scope_names": [scope_name] if scope_name else [],
                "fact_type": row.get("fact_type"),
                "fact_key": row.get("fact_key"),
            }
        )
    inventory = {
        "fact_count": len(rows),
        "scope_counts": {},
        "segment_count": len(segments),
    }
    for row in rows:
        key = row.get("scope_level") or "unknown"
        inventory["scope_counts"][key] = inventory["scope_counts"].get(key, 0) + 1

    inventory_id = hashlib.sha256(f"{company_id}:{event_id}:{document_id}:inventory".encode()).hexdigest()
    conn.execute(
        """
        INSERT INTO presentation_document_inventory (
            id, company_id, event_id, document_id, period_label,
            inventory_json, extraction_plan_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            period_label = excluded.period_label,
            inventory_json = excluded.inventory_json,
            extraction_plan_json = excluded.extraction_plan_json
        """,
        (
            inventory_id,
            company_id,
            event_id,
            document_id,
            period_label,
            json.dumps(inventory, sort_keys=True),
            json.dumps({"slide_plan": slide_plan}, sort_keys=True),
        ),
    )
    conn.execute(
        "DELETE FROM presentation_segments WHERE company_id = ? AND event_id = ? AND document_id = ?",
        (company_id, event_id, document_id),
    )
    for name, segment in segments.items():
        segment_id = hashlib.sha256(f"{company_id}:{event_id}:{document_id}:{name}".encode()).hexdigest()
        conn.execute(
            """
            INSERT INTO presentation_segments (
                id, company_id, event_id, document_id, segment_name,
                segment_slug, aliases_json, slides_json, confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                segment_id,
                company_id,
                event_id,
                document_id,
                name,
                _slug(name),
                json.dumps(segment["aliases"]),
                json.dumps(sorted(segment["slides"])),
                segment["confidence"],
            ),
        )


def persist_presentation_values(
    conn: sqlite3.Connection,
    *,
    company_id: str,
    event_id: str,
    document_id: str,
    period_quarter: int,
    period_fy_start: int,
    period_end: str,
    rows: list[dict[str, Any]],
    facts_catalog: dict[str, Any],
    preferred_source: str = "investor_presentation",
) -> None:
    seed_fact_definitions(
        conn,
        facts_catalog=facts_catalog,
        preferred_source=preferred_source,
    )
    for row in rows:
        conn.execute(
            """
            INSERT INTO extracted_values (
                id, company_id, event_id, value_code, value_numeric, value_text, unit,
                period_type, period_start, period_end, basis, segment, geography,
                product, channel, project, customer_type, metric_context,
                scope_level, scope_name, fact_type, value_lower, value_upper,
                sentiment, is_explicit_guidance, source_text, source_page, confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'quarter', NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                event_id = excluded.event_id,
                value_numeric = excluded.value_numeric,
                value_text = excluded.value_text,
                unit = excluded.unit,
                basis = excluded.basis,
                segment = excluded.segment,
                geography = excluded.geography,
                product = excluded.product,
                channel = excluded.channel,
                project = excluded.project,
                customer_type = excluded.customer_type,
                metric_context = excluded.metric_context,
                scope_level = excluded.scope_level,
                scope_name = excluded.scope_name,
                fact_type = excluded.fact_type,
                value_lower = excluded.value_lower,
                value_upper = excluded.value_upper,
                sentiment = excluded.sentiment,
                is_explicit_guidance = excluded.is_explicit_guidance,
                source_text = excluded.source_text,
                source_page = excluded.source_page,
                confidence = excluded.confidence
            """,
            (
                presentation_value_id(company_id, row, period_end),
                company_id,
                event_id,
                row["fact_key"],
                row["numeric_value"],
                row["value_text"],
                row["unit"],
                period_end,
                row["basis"],
                row["segment"],
                row["geography"],
                row.get("product"),
                row.get("channel"),
                row.get("project"),
                row.get("customer_type"),
                row.get("metric_context"),
                row.get("scope_level"),
                row.get("scope_name"),
                row.get("fact_type"),
                row.get("value_lower"),
                row.get("value_upper"),
                row.get("sentiment"),
                row.get("is_explicit_guidance"),
                row["source_text"],
                row.get("source_page"),
                row["confidence"],
            ),
        )
    persist_fact_observations_and_resolutions(
        conn,
        company_id=company_id,
        event_id=event_id,
        document_id=document_id,
        period_end=period_end,
        rows=rows,
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
    pdf_url: str | None,
    pdf_bytes: bytes,
    event_type: str = "Financial Results",
    document_type: str | None = None,
    local_path: str | None = None,
    force_reparse: bool = False,
    parse_max_workers: int | None = None,
    extraction_max_workers: int | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    overall_started = time.monotonic()

    def progress(phase: str, message: str, **extra: Any) -> None:
        payload = {
            "phase": phase,
            "message": message,
            "elapsed_seconds": round(time.monotonic() - overall_started, 1),
            **extra,
        }
        logger.info(
            "VALUES progress phase=%s elapsed=%.1fs %s",
            phase,
            payload["elapsed_seconds"],
            message,
        )
        if progress_callback is not None:
            progress_callback(payload)

    parse_workers = parse_max_workers or settings.parse_max_workers
    extraction_workers = extraction_max_workers or settings.extraction_max_workers
    progress(
        "init",
        "Validating request and preparing document",
        symbol=symbol,
        event_id=event_id,
        event_type=event_type,
        parse_workers=parse_workers,
        extraction_workers=extraction_workers,
        force_reparse=force_reparse,
    )
    expected_company_id = company_id_for_symbol(symbol)
    if company_id != expected_company_id:
        raise ValueError("company_id does not match the NSE symbol-derived company id")

    bootstrap_schema(conn)
    event_row = _event_context(conn, event_id)
    event_type = event_type or str(event_row.get("event_type") or "Financial Results")
    if document_type is None:
        document_type = {
            "Financial Results": "financial_result",
            "Investor Presentation": "investor_presentation",
            "Earnings Call Transcript": "earnings_call_transcript",
        }.get(event_type, "financial_result")
    source_ref = pdf_url or local_path or ""
    title = _document_title(event_row, source_ref)
    document_kind = {
        "financial_result": "FINANCIAL_RESULT",
        "investor_presentation": "INVESTOR_PRESENTATION",
        "earnings_call_transcript": "EARNINGS_CALL_TRANSCRIPT",
    }.get(document_type, "FINANCIAL_RESULT")
    stored_doc = store_document(
        conn,
        company_id=company_id,
        event_id=event_id,
        pdf_url=source_ref,
        pdf_bytes=pdf_bytes,
        title=title,
        document_kind=document_kind,
    )
    progress(
        "stored_document",
        "Stored source document and linked it to the event",
        document_id=stored_doc["document_id"],
        storage_path=str(stored_doc["storage_path"]),
        bytes=len(pdf_bytes),
        source=source_ref,
    )

    openai_api_key = load_env_value("OPENAI_API_KEY")
    openai_model = load_env_value("OPENAI_MODEL") or "gpt-4.1-mini"
    openai_parse_model = load_env_value("OPENAI_PARSE_MODEL") or openai_model
    openai_summary_model = load_env_value("OPENAI_SUMMARY_MODEL") or "gpt-4.1-mini"
    if not openai_api_key:
        raise RuntimeError(f"OPENAI_API_KEY not found in {settings.env_path}")

    from openai import OpenAI

    client = OpenAI(
        api_key=openai_api_key,
        timeout=settings.openai_timeout_seconds,
        max_retries=settings.openai_max_retries,
    )
    logger.info(
        "Starting value extraction for %s event_id=%s event_type=%s document_type=%s parse_model=%s extraction_model=%s force_reparse=%s",
        symbol,
        event_id,
        event_type,
        document_type,
        openai_parse_model,
        openai_model,
        force_reparse,
    )
    if pdf_bytes[:4] == b"%PDF":
        progress(
            "parse_pdf",
            "Parsing PDF to markdown",
            document_id=stored_doc["document_id"],
            parse_model=openai_parse_model,
        )

        def parse_progress(update: dict[str, Any]) -> None:
            phase = str(update.get("phase") or "parse_pdf")
            message = str(update.get("message") or "PDF parse progress")
            extra = {
                key: value
                for key, value in update.items()
                if key not in {"phase", "message", "elapsed_seconds"}
            }
            progress(phase, message, **extra)

        markdown = parse_pdf_to_markdown(
            stored_doc["storage_path"],
            parsed_dir=settings.parsed_dir,
            client=client,
            model=openai_parse_model,
            force=force_reparse,
            max_workers=parse_workers,
            progress_callback=parse_progress,
        )
        logger.info("PDF markdown ready: %s chars", len(markdown))
        progress(
            "markdown_ready",
            "PDF markdown is ready",
            markdown_chars=len(markdown),
        )
    else:
        markdown = pdf_bytes.decode("utf-8", errors="replace")
        logger.info("Text document ready: %s chars", len(markdown))
        progress("markdown_ready", "Text document is ready", markdown_chars=len(markdown))

    progress("detect_period", "Detecting reporting period", title=title)
    reporting_period = detect_period(markdown, title=title, event_row=event_row)
    period_end = reporting_period.quarter_end
    progress(
        "period_detected",
        "Reporting period detected",
        period_label=reporting_period.label,
        period_end=period_end,
        quarter=reporting_period.quarter,
        fy_start_year=reporting_period.fy_start_year,
    )

    try:
        progress(
            "generate_summary",
            "Generating professional filing summary",
            model=openai_summary_model,
        )
        summary_result = generate_event_summary_for_event(
            conn,
            client=client,
            model=openai_summary_model,
            event_id=event_id,
        )
        progress(
            "summary_ready",
            "Filing summary is ready",
            model=summary_result["model"],
            cached=summary_result["cached"],
        )
    except Exception:
        # Summary quality must not block the deterministic extraction pipeline.
        logger.exception("Could not generate filing summary for event %s", event_id)
        progress(
            "summary_skipped",
            "Filing summary could not be generated; extraction will continue",
        )

    if event_type in {"Investor Presentation", "Earnings Call Transcript"}:
        progress("load_catalog", "Loading unified document facts catalog", event_type=event_type)
        facts_catalog = (
            load_presentation_facts_catalog()
            if event_type == "Investor Presentation"
            else load_earnings_call_facts_catalog()
        )
        storage_to_fact, fact_catalog_text = _presentation_catalog_aliases(facts_catalog)
        chunks = _chunk(markdown, max_chars=14000)
        workers = min(max(extraction_workers, 1), len(chunks)) if chunks else 1
        logger.info(
            "Running %s extraction over %s markdown chunks with %s worker(s)",
            event_type,
            len(chunks),
            workers,
        )
        progress(
            "llm_extract",
            f"Running {event_type} extraction",
            chunks=len(chunks),
            workers=workers,
            model=openai_model,
        )

        def extract_unified_chunk(index: int, chunk: str) -> tuple[int, list[dict[str, Any]]]:
            started = time.monotonic()
            progress(
                "llm_extract_chunk",
                f"Started {event_type} chunk {index}/{len(chunks)}",
                chunk=index,
                chunks=len(chunks),
                chunk_chars=len(chunk),
            )
            if event_type == "Investor Presentation":
                chunk_facts = extract_presentation_facts_from_chunk(
                    client,
                    model=openai_model,
                    chunk=chunk,
                    symbol=symbol,
                    period_label=reporting_period.label,
                    period_end=period_end,
                    fact_catalog_text=fact_catalog_text,
                )
            else:
                chunk_facts = extract_unified_document_facts_from_chunk(
                    client,
                    model=openai_model,
                    chunk=chunk,
                    symbol=symbol,
                    document_type=document_type,
                    period_label=reporting_period.label,
                    period_end=period_end,
                    fact_catalog_text=fact_catalog_text,
                )
            logger.info(
                "%s extraction chunk %s/%s returned %s candidate facts in %.1fs",
                event_type,
                index,
                len(chunks),
                len(chunk_facts),
                time.monotonic() - started,
            )
            progress(
                "llm_extract_chunk",
                f"Finished {event_type} chunk {index}/{len(chunks)}",
                chunk=index,
                chunks=len(chunks),
                candidate_facts=len(chunk_facts),
                chunk_elapsed_seconds=round(time.monotonic() - started, 1),
            )
            return index, chunk_facts

        if workers == 1:
            chunk_results = [
                extract_unified_chunk(index, chunk)
                for index, chunk in enumerate(chunks, start=1)
            ]
        else:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [
                    executor.submit(extract_unified_chunk, index, chunk)
                    for index, chunk in enumerate(chunks, start=1)
                ]
                chunk_results = [future.result() for future in as_completed(futures)]

        raw_facts: list[dict[str, Any]] = []
        for _, chunk_facts in sorted(chunk_results, key=lambda item: item[0]):
            raw_facts.extend(chunk_facts)
        accepted_rows = canonicalize_presentation_facts(
            raw_facts,
            facts_catalog=facts_catalog,
            storage_to_fact=storage_to_fact,
        )
        progress(
            "validate_facts",
            "Validated unified document facts",
            raw_facts=len(raw_facts),
            accepted_rows=len(accepted_rows),
        )
        if not accepted_rows:
            raise RuntimeError("No presentation facts passed validation after extraction")

        progress("persist_values", "Persisting extracted values", rows=len(accepted_rows))
        persist_presentation_values(
            conn,
            company_id=company_id,
            event_id=event_id,
            document_id=stored_doc["document_id"],
            period_quarter=reporting_period.quarter,
            period_fy_start=reporting_period.fy_start_year,
            period_end=period_end,
            rows=accepted_rows,
            facts_catalog=facts_catalog,
            preferred_source=document_type,
        )
        if event_type == "Investor Presentation":
            persist_presentation_inventory(
                conn,
                company_id=company_id,
                event_id=event_id,
                document_id=stored_doc["document_id"],
                period_label=reporting_period.label,
                rows=accepted_rows,
            )
            conn.commit()
        progress(
            "complete",
            "Step 4 completed",
            rows=len(accepted_rows),
            document_id=stored_doc["document_id"],
        )

        return {
            "document_id": stored_doc["document_id"],
            "storage_path": str(stored_doc["storage_path"]),
            "markdown_length": len(markdown),
            "reporting_period": reporting_period.to_dict(),
            "values": accepted_rows,
        }

    progress("load_catalog", "Loading financial results facts catalog")
    facts_catalog = load_facts_catalog()
    storage_to_fact, fact_catalog_text = _catalog_aliases(facts_catalog)
    company_row = conn.execute(
        "SELECT name FROM companies WHERE id = ?", (company_id,)
    ).fetchone()
    company_name = str(company_row["name"] if company_row is not None else symbol)
    unsafe_multi_issuer_publication = is_multi_issuer_newspaper(markdown)
    progress(
        "deterministic_extract",
        "Running deterministic period-column extraction",
        catalog_keys=len(facts_catalog),
        unsafe_multi_issuer_publication=unsafe_multi_issuer_publication,
    )
    deterministic_facts = []
    if not unsafe_multi_issuer_publication:
        deterministic_facts = extract_facts_from_quarter_column(
            markdown,
            target=reporting_period,
            fact_keys=set(facts_catalog.keys()),
            facts_catalog=facts_catalog,
        )
    deterministic_by_key = {row["fact_key"]: row for row in deterministic_facts}
    raw_facts: list[dict[str, Any]] = list(deterministic_facts)
    missing_keys = set(facts_catalog.keys()) - set(deterministic_by_key)
    logger.info(
        "Deterministic extraction found %s facts; %s catalog keys still missing",
        len(deterministic_facts),
        len(missing_keys),
    )
    progress(
        "deterministic_extract",
        "Deterministic extraction completed",
        found_facts=len(deterministic_facts),
        missing_keys=len(missing_keys),
    )

    if missing_keys and not unsafe_multi_issuer_publication:
        chunks = _chunk_financial_markdown(markdown)
        workers = min(max(extraction_workers, 1), len(chunks)) if chunks else 1
        logger.info(
            "Running LLM fallback over %s markdown chunks with %s worker(s) for missing facts",
            len(chunks),
            workers,
        )
        progress(
            "llm_fallback",
            "Running LLM fallback for missing facts",
            chunks=len(chunks),
            workers=workers,
            missing_keys=len(missing_keys),
            model=openai_model,
        )
    else:
        chunks = []
        workers = 1
        if unsafe_multi_issuer_publication:
            logger.warning("Withholding extraction from multi-issuer newspaper publication")
            progress(
                "llm_fallback_skipped",
                "Withheld unsafe multi-issuer newspaper publication",
                decision="abstain",
            )
        else:
            logger.info("Skipping LLM fallback; deterministic extraction covered the catalog")
            progress("llm_fallback_skipped", "Deterministic extraction covered the catalog")

    def extract_chunk(index: int, chunk: str) -> tuple[int, list[dict[str, Any]]]:
        started = time.monotonic()
        progress(
            "llm_fallback_chunk",
            f"Started LLM fallback chunk {index}/{len(chunks)}",
            chunk=index,
            chunks=len(chunks),
            chunk_chars=len(chunk),
        )
        chunk_facts = extract_facts_from_chunk(
            client,
            model=openai_model,
            chunk=chunk,
            symbol=symbol,
            company_name=company_name,
            period_label=reporting_period.label,
            period_end=period_end,
            fact_catalog_text=fact_catalog_text,
        )
        logger.info(
            "LLM fallback chunk %s/%s returned %s candidate facts in %.1fs",
            index,
            len(chunks),
            len(chunk_facts),
            time.monotonic() - started,
        )
        progress(
            "llm_fallback_chunk",
            f"Finished LLM fallback chunk {index}/{len(chunks)}",
            chunk=index,
            chunks=len(chunks),
            candidate_facts=len(chunk_facts),
            chunk_elapsed_seconds=round(time.monotonic() - started, 1),
        )
        return index, chunk_facts

    chunk_results: list[tuple[int, list[dict[str, Any]]]] = []
    if chunks and workers == 1:
        chunk_results = [extract_chunk(index, chunk) for index, chunk in enumerate(chunks, start=1)]
    elif chunks:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(extract_chunk, index, chunk)
                for index, chunk in enumerate(chunks, start=1)
            ]
            chunk_results = [future.result() for future in as_completed(futures)]

    for _, chunk_facts in sorted(chunk_results, key=lambda item: item[0]):
        for entry in chunk_facts:
            fact_key = entry.get("fact_key")
            canonical = storage_to_fact.get(str(fact_key), str(fact_key)) if fact_key else None
            if canonical and canonical in deterministic_by_key:
                continue
            if canonical and canonical not in missing_keys:
                continue
            entry.setdefault("period_end", period_end)
            entry.setdefault("extraction_method", "llm_fallback")
            raw_facts.append(entry)

    accepted_rows = canonicalize_facts(
        raw_facts,
        facts_catalog=facts_catalog,
        storage_to_fact=storage_to_fact,
    )
    progress(
        "validate_facts",
        "Validated financial result facts",
        raw_facts=len(raw_facts),
        accepted_rows=len(accepted_rows),
    )
    if not accepted_rows:
        if not unsafe_multi_issuer_publication:
            raise RuntimeError("No facts passed validation after extraction")
        persist_extracted_values(
            conn,
            company_id=company_id,
            event_id=event_id,
            document_id=stored_doc["document_id"],
            period_quarter=reporting_period.quarter,
            period_fy_start=reporting_period.fy_start_year,
            period_end=period_end,
            rows=[],
            facts_catalog=facts_catalog,
        )
        return {
            "document_id": stored_doc["document_id"],
            "storage_path": str(stored_doc["storage_path"]),
            "markdown_length": len(markdown),
            "reporting_period": reporting_period.to_dict(),
            "values": [],
            "decision": "abstain",
            "abstention_reason": "multi_issuer_newspaper_publication",
        }

    progress("persist_values", "Persisting extracted values", rows=len(accepted_rows))
    persist_extracted_values(
        conn,
        company_id=company_id,
        event_id=event_id,
        document_id=stored_doc["document_id"],
        period_quarter=reporting_period.quarter,
        period_fy_start=reporting_period.fy_start_year,
        period_end=period_end,
        rows=accepted_rows,
        facts_catalog=facts_catalog,
    )
    progress(
        "complete",
        "Step 4 completed",
        rows=len(accepted_rows),
        document_id=stored_doc["document_id"],
    )

    return {
        "document_id": stored_doc["document_id"],
        "storage_path": str(stored_doc["storage_path"]),
        "markdown_length": len(markdown),
        "reporting_period": reporting_period.to_dict(),
        "values": accepted_rows,
    }
