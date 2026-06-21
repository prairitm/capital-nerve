"""PDF → markdown parsing for Capital Nerve (page-by-page LLM)."""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any

import fitz

SUMMARY_RED_FLAG_PATTERNS = (
    r"continue in similar",
    r"comprehensive data present",
    r"maintaining the comprehensive",
    r"similar structured tables",
    r"remaining sections",
    r"further financial statements continue",
    r"overall notes and further",
)

PAGE_PROMPT_TEMPLATE = """Convert this single page (page {page_num} of {page_total}) of an Indian corporate financial filing PDF to markdown.

Requirements:
- Transcribe ONLY content visible on this page — do not refer to or summarize other pages
- Preserve every table as a markdown table with correct columns and numeric values
- Use markdown headings (#, ##, ###) for section titles that appear on this page
- Keep line items, notes, and footnotes in reading order
- Do not summarize, omit, paraphrase, or invent data
- Do NOT write meta-commentary (forbidden: "similar tables follow", "remaining sections", "continues below")
- Output markdown only — no preamble or explanation"""


def pdf_page_count(pdf_path: str | Path) -> int:
    with fitz.open(pdf_path) as doc:
        return doc.page_count


def extract_pdf_text(pdf_path: str | Path) -> str:
    with fitz.open(pdf_path) as doc:
        return "".join(page.get_text() for page in doc)


def has_summary_filler(markdown: str) -> bool:
    lower = markdown.lower()
    return any(re.search(pat, lower) for pat in SUMMARY_RED_FLAG_PATTERNS)


def validate_parsed_markdown(markdown: str, pdf_path: str | Path) -> list[str]:
    """Return validation issue codes; empty list means acceptable."""
    issues: list[str] = []
    if has_summary_filler(markdown):
        issues.append("summary_filler_detected")

    pdf_text = extract_pdf_text(pdf_path).lower()
    md_lower = markdown.lower()

    if re.search(r"consolidated\s+financial\s+results", pdf_text):
        if not re.search(r"consolidated\s+financial", md_lower):
            issues.append("missing_consolidated_section")

    if re.search(r"standalone\s+financial\s+results", pdf_text):
        if not re.search(r"standalone\s+financial", md_lower):
            issues.append("missing_standalone_section")

    pdf_len = len(pdf_text)
    if pdf_len > 5000 and len(markdown) < pdf_len * 0.25:
        issues.append("markdown_too_short_vs_pdf")

    return issues


def write_single_page_pdf(src: Path, page_index: int, dest: Path) -> None:
    with fitz.open(src) as doc:
        single = fitz.open()
        try:
            single.insert_pdf(doc, from_page=page_index, to_page=page_index)
            single.save(dest)
        finally:
            single.close()


def pdf_to_markdown_page_by_page(
    storage_path: str | Path,
    *,
    client: Any,
    model: str,
    max_output_tokens: int = 8192,
    on_page_done: Any | None = None,
) -> str:
    """Convert a PDF to markdown via one LLM call per page."""
    path = Path(storage_path)
    total = pdf_page_count(path)
    if total == 0:
        raise RuntimeError(f"PDF has no pages: {path.name}")

    parts: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for i in range(total):
            page_pdf = tmp_dir / f"page_{i + 1:03d}.pdf"
            write_single_page_pdf(path, i, page_pdf)

            with page_pdf.open("rb") as fh:
                uploaded = client.files.create(file=fh, purpose="user_data")
            try:
                prompt = PAGE_PROMPT_TEMPLATE.format(page_num=i + 1, page_total=total)
                response = client.responses.create(
                    model=model,
                    input=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "input_text", "text": prompt},
                                {
                                    "type": "input_file",
                                    "file_id": uploaded.id,
                                    "detail": "high",
                                },
                            ],
                        }
                    ],
                    max_output_tokens=max_output_tokens,
                )
                page_md = (response.output_text or "").strip()
                if not page_md:
                    raise RuntimeError(
                        f"Empty markdown for page {i + 1}/{total} of {path.name}"
                    )
                parts.append(page_md)
                if on_page_done:
                    on_page_done(i + 1, total)
            finally:
                client.files.delete(uploaded.id)

    return "\n\n".join(parts)


def read_parse_meta(meta_path: Path) -> dict[str, Any]:
    if not meta_path.exists():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def write_parse_meta(meta_path: Path, *, source_sha256: str, page_count: int) -> None:
    meta_path.write_text(
        json.dumps(
            {"source_sha256": source_sha256, "page_count": page_count, "mode": "page_by_page"},
            indent=2,
        ),
        encoding="utf-8",
    )


def should_reparse(
    md_path: Path,
    pdf_path: Path,
    *,
    source_sha256: str | None = None,
    force: bool = False,
) -> bool:
    if force:
        return True
    if not md_path.exists():
        return True

    meta = read_parse_meta(md_path.with_suffix(".meta.json"))
    if source_sha256 and meta.get("source_sha256") != source_sha256:
        return True

    issues = validate_parsed_markdown(md_path.read_text(encoding="utf-8"), pdf_path)
    return bool(issues)
