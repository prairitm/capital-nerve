"""PDF → markdown via OpenAI vision (page-by-page).

Mirrors the ``capital_nerve_parse`` API used by v3 so the notebook and pipeline
can share one parse path without an external package.
"""

from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import logging
import time
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("uvicorn.error")

_PAGE_DPI = 200
_PARSE_PROMPT = """Convert this Indian corporate filing page to clean markdown.

Rules:
- Preserve tables as markdown pipe tables with correct row/column alignment
- Keep every number exactly as printed (commas, parentheses for negatives, decimals)
- Include column headers and period dates (e.g. Quarter Ended 31.03.2025)
- Use # headings for page titles; do not wrap the whole page in a code block
- Omit decorative letterhead art; keep all financial statement content
- If the page has no meaningful content, return a single line: *(empty page)*
"""


def should_reparse(
    md_path: Path,
    pdf_path: Path,
    *,
    source_sha256: str,
    force: bool = False,
) -> bool:
    if force or not md_path.exists():
        return True
    meta_path = md_path.with_suffix(".meta.json")
    if not meta_path.exists():
        return True
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    return meta.get("source_sha256") != source_sha256


def write_parse_meta(
    meta_path: Path,
    *,
    source_sha256: str,
    page_count: int,
) -> None:
    meta_path.write_text(
        json.dumps(
            {
                "source_sha256": source_sha256,
                "page_count": page_count,
                "mode": "page_by_page",
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _page_png_b64(pdf_path: Path, page_index: int) -> str:
    import fitz

    with fitz.open(pdf_path) as doc:
        page = doc[page_index]
        pix = page.get_pixmap(dpi=_PAGE_DPI)
        return base64.standard_b64encode(pix.tobytes("png")).decode("ascii")


def _parse_page_image(client: Any, *, model: str, png_b64: str, page_no: int) -> str:
    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": _PARSE_PROMPT},
                    {
                        "type": "input_image",
                        "image_url": f"data:image/png;base64,{png_b64}",
                    },
                ],
            }
        ],
        temperature=0,
    )
    text = (response.output_text or "").strip()
    if not text:
        return f"*(empty page {page_no})*"
    return text


def pdf_to_markdown_page_by_page(
    pdf_path: Path,
    *,
    client: Any,
    model: str,
    max_workers: int = 1,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> str:
    import fitz

    with fitz.open(pdf_path) as doc:
        page_count = doc.page_count

    workers = max(1, min(max_workers, page_count))
    parts = [""] * page_count
    logger.info(
        "Parsing PDF %s page-by-page: %s pages with %s worker(s)",
        pdf_path.name,
        page_count,
        workers,
    )
    if progress_callback is not None:
        progress_callback(
            {
                "phase": "parse_pdf",
                "message": "Started page-by-page PDF parsing",
                "pdf": pdf_path.name,
                "pages": page_count,
                "workers": workers,
            }
        )

    def parse_page(i: int) -> tuple[int, str]:
        started = time.monotonic()
        if progress_callback is not None:
            progress_callback(
                {
                    "phase": "parse_pdf_page",
                    "message": f"Started parsing page {i + 1}/{page_count}",
                    "page": i + 1,
                    "pages": page_count,
                }
            )
        png_b64 = _page_png_b64(pdf_path, i)
        page_md = _parse_page_image(client, model=model, png_b64=png_b64, page_no=i + 1)
        elapsed = time.monotonic() - started
        logger.info(
            "Parsed PDF page %s/%s in %.1fs",
            i + 1,
            page_count,
            elapsed,
        )
        if progress_callback is not None:
            progress_callback(
                {
                    "phase": "parse_pdf_page",
                    "message": f"Finished parsing page {i + 1}/{page_count}",
                    "page": i + 1,
                    "pages": page_count,
                    "page_elapsed_seconds": round(elapsed, 1),
                }
            )
        return i, f"# Page {i + 1}\n\n{page_md}"

    if workers == 1:
        for i in range(page_count):
            index, page_text = parse_page(i)
            parts[index] = page_text
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(parse_page, i) for i in range(page_count)]
            for future in as_completed(futures):
                index, page_text = future.result()
                parts[index] = page_text

    return "\n\n---\n\n".join(parts)


def parse_pdf_to_markdown(
    pdf_path: Path,
    *,
    parsed_dir: Path,
    client: Any,
    model: str,
    force: bool = False,
    max_workers: int = 1,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> str:
    """Parse PDF to markdown with disk cache under ``parsed_dir``."""
    import hashlib

    parsed_dir.mkdir(parents=True, exist_ok=True)
    md_path = parsed_dir / f"{pdf_path.stem}.md"
    digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()

    if not should_reparse(md_path, pdf_path, source_sha256=digest, force=force):
        logger.info("Using cached PDF markdown: %s", md_path)
        if progress_callback is not None:
            progress_callback(
                {
                    "phase": "parse_pdf_cache",
                    "message": "Using cached PDF markdown",
                    "markdown_path": str(md_path),
                }
            )
        return md_path.read_text(encoding="utf-8")

    started = time.monotonic()
    markdown = pdf_to_markdown_page_by_page(
        pdf_path,
        client=client,
        model=model,
        max_workers=max_workers,
        progress_callback=progress_callback,
    )
    md_path.write_text(markdown, encoding="utf-8")
    write_parse_meta(
        md_path.with_suffix(".meta.json"),
        source_sha256=digest,
        page_count=sum(1 for line in markdown.splitlines() if line.startswith("# Page ")),
    )
    logger.info("Wrote PDF markdown cache %s in %.1fs", md_path, time.monotonic() - started)
    return markdown
