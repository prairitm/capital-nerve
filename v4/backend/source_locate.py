"""Locate a source quote inside a document's parsed markdown or PDF text layer."""

from __future__ import annotations

import re
from pathlib import Path

_LINE_PREFIX_RE = re.compile(r"^(\d+)\.\s*", re.MULTILINE)
_PAGE_HEADER_RE = re.compile(r"^# Page (\d+)\s*$", re.MULTILINE)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _source_label(source_text: str) -> str:
    label = source_text.strip().split("|")[0].strip()
    label = re.sub(r"^\d+\.\s*", "", label)
    return label.strip()


def _extract_tokens(source_text: str) -> list[str]:
    text = source_text.strip()
    tokens: list[str] = []
    m = re.match(r"^(\d+)\.", text)
    if m:
        tokens.append(f"{m.group(1)}.")
    for num in re.findall(r"-?[\d,]+\.?\d*", text):
        clean = num.replace(",", "")
        if clean and len(clean) >= 2 and clean not in {"10", "31", "12"}:
            tokens.append(clean)
    words = re.findall(r"[a-zA-Z]{4,}", text)
    tokens.extend(w.lower() for w in words[:8])
    return tokens


def _score_page_text(page_text: str, source_text: str) -> int:
    norm_page = _normalize(page_text)
    norm_quote = _normalize(source_text)
    label = _normalize(_source_label(source_text))

    if norm_quote and norm_quote in norm_page:
        return 100
    if label and len(label) >= 8 and label in norm_page:
        return 80

    score = 0
    m = re.match(r"^(\d+)\.", source_text.strip())
    if m and f"{m.group(1)}." in page_text:
        score += 4

    for token in _extract_tokens(source_text):
        if token in norm_page or token in page_text:
            score += 1
    return score


def _reference_snippet(md: str, source_text: str) -> str:
    label = _source_label(source_text)
    for needle in (source_text, label):
        if not needle:
            continue
        idx = md.lower().find(needle.lower()[: min(60, len(needle))])
        if idx >= 0:
            start = max(0, idx - 300)
            end = min(len(md), idx + 1500)
            return md[start:end]
    return md[:4000]


def _pages_from_markdown(md: str) -> list[tuple[int, str]]:
    if not _PAGE_HEADER_RE.search(md):
        return []
    parts = _PAGE_HEADER_RE.split(md)
    pages: list[tuple[int, str]] = []
    for i in range(1, len(parts), 2):
        pages.append((int(parts[i]), parts[i + 1]))
    return pages


def locate_in_markdown(md_path: Path, source_text: str) -> tuple[int | None, str | None]:
    if not md_path.exists():
        return None, None
    md = md_path.read_text(encoding="utf-8")
    pages = _pages_from_markdown(md)
    if not pages:
        # Unpaginated parse cache — keep text for highlighting, resolve page via PDF.
        score = _score_page_text(md, source_text)
        if score >= 5:
            return None, _reference_snippet(md, source_text)
        return None, None

    best_page: int | None = None
    best_score = 0
    best_ref: str | None = None
    for page_num, content in pages:
        score = _score_page_text(content, source_text)
        if score > best_score:
            best_score = score
            best_page = page_num
            best_ref = content
    if best_score < 4:
        return None, None
    return best_page, (best_ref[:4000] if best_ref else None)


def locate_in_pdf(pdf_path: Path, source_text: str) -> int | None:
    try:
        import fitz
    except ImportError:
        return None

    if not pdf_path.exists():
        return None

    best_page: int | None = None
    best_score = 0
    with fitz.open(pdf_path) as doc:
        for i in range(doc.page_count):
            score = _score_page_text(doc[i].get_text(), source_text)
            if score > best_score:
                best_score = score
                best_page = i + 1
    return best_page if best_score >= 4 else None


def locate_source(
    *,
    parsed_md_path: Path,
    pdf_path: Path,
    source_text: str,
) -> dict[str, int | str | None]:
    page, reference_text = locate_in_markdown(parsed_md_path, source_text)
    if page is None:
        page = locate_in_pdf(pdf_path, source_text)
    return {
        "page": page,
        "reference_text": reference_text,
    }
