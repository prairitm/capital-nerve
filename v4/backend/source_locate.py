"""Locate a source quote inside a document's parsed markdown or PDF text layer."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

_LINE_PREFIX_RE = re.compile(r"^(\d+)\.\s*", re.MULTILINE)
_PAGE_HEADER_RE = re.compile(r"^# Page (\d+)\s*$", re.MULTILINE)
_NUMBER_RE = re.compile(r"\(?[-+]?\d[\d,]*(?:\.\d+)?\)?")


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _canonical_number(raw: str) -> str | None:
    text = (
        raw.strip()
        .replace(",", "")
        .replace("₹", "")
        .replace("$", "")
        .replace("€", "")
        .replace("£", "")
        .replace("−", "-")
        .replace("–", "-")
        .replace("—", "-")
    )
    text = re.sub(r"\s+", "", text)
    paren_negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    if paren_negative and not text.startswith("-"):
        text = f"-{text}"
    if not re.fullmatch(r"[-+]?\d+(?:\.\d+)?", text):
        return None
    negative = text.startswith("-")
    unsigned = text.lstrip("+-")
    whole, _, frac = unsigned.partition(".")
    whole = whole.lstrip("0") or "0"
    frac = frac.rstrip("0")
    return f"{'-' if negative else ''}{whole}{'.' + frac if frac else ''}"


def _numbers_equal(a: str, b: str) -> bool:
    ca = _canonical_number(a)
    cb = _canonical_number(b)
    return bool(ca and cb and ca == cb)


def _source_label(source_text: str) -> str:
    label = source_text.strip().split("|")[0].strip()
    label = re.sub(r"^\d+\.\s*", "", label)
    return label.strip()


def _source_label_for_match(source_text: str) -> str:
    label = _source_label(source_text)
    label = _NUMBER_RE.sub(" ", label)
    label = re.sub(r"\s+", " ", label)
    return label.strip(" |:-")


def _label_words(source_text: str) -> list[str]:
    return [
        word.lower()
        for word in re.findall(r"[a-zA-Z]{4,}", _source_label_for_match(source_text))
    ]


def _target_numbers(
    source_text: str,
    target_value: str | None = None,
    *,
    include_source_numbers: bool = True,
) -> list[str]:
    numbers: list[str] = []
    seen: set[str] = set()

    def add(raw: str | None) -> None:
        if not raw:
            return
        canonical = _canonical_number(raw)
        if not canonical or canonical in seen:
            return
        seen.add(canonical)
        numbers.append(raw)

    add(target_value)
    if target_value and _canonical_number(target_value):
        return numbers
    if not include_source_numbers:
        return numbers
    for num in _NUMBER_RE.findall(source_text):
        digits = re.sub(r"\D", "", num)
        if len(digits) >= 2:
            add(num)
    return numbers


def _extract_tokens(source_text: str, target_value: str | None = None) -> list[str]:
    text = source_text.strip()
    tokens: list[str] = []
    m = re.match(r"^(\d+)\.", text)
    if m:
        tokens.append(f"{m.group(1)}.")
    for num in _target_numbers(
        source_text,
        target_value,
        include_source_numbers=not bool(target_value),
    ):
        clean = num.replace(",", "")
        if clean and len(clean) >= 2 and clean not in {"10", "31", "12"}:
            tokens.append(clean)
    words = re.findall(r"[a-zA-Z]{4,}", text)
    tokens.extend(w.lower() for w in words[:8])
    return tokens


def _page_has_target_number(page_text: str, source_text: str, target_value: str | None) -> bool:
    targets = _target_numbers(
        source_text,
        target_value,
        include_source_numbers=not bool(target_value),
    )
    if not targets:
        return False
    page_numbers = _NUMBER_RE.findall(page_text)
    return any(_numbers_equal(page_num, target) for page_num in page_numbers for target in targets)


def _score_page_text(
    page_text: str,
    source_text: str,
    target_value: str | None = None,
    context: str | None = None,
) -> int:
    norm_page = _normalize(page_text)
    norm_quote = _normalize(source_text)
    label = _normalize(_source_label(source_text))
    match_label = _normalize(_source_label_for_match(source_text))

    if norm_quote and norm_quote in norm_page:
        return 100

    score = 0
    if label and len(label) >= 8 and label in norm_page:
        score += 30
    if match_label and len(match_label) >= 8 and match_label in norm_page:
        score += 25
    m = re.match(r"^(\d+)\.", source_text.strip())
    if m and f"{m.group(1)}." in page_text:
        score += 4

    if _page_has_target_number(page_text, source_text, target_value):
        score += 50

    if context:
        context_norm = _normalize(context)
        if context_norm and context_norm in norm_page:
            score += 20

    for word in _label_words(source_text):
        if word in norm_page:
            score += 1

    for token in _extract_tokens(source_text, target_value):
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


def _page_content_from_markdown(md: str, page_num: int) -> str | None:
    pages = _pages_from_markdown(md)
    for num, content in pages:
        if num == page_num:
            return content[:4000]
    return None


def _pages_from_markdown(md: str) -> list[tuple[int, str]]:
    if not _PAGE_HEADER_RE.search(md):
        return []
    parts = _PAGE_HEADER_RE.split(md)
    pages: list[tuple[int, str]] = []
    for i in range(1, len(parts), 2):
        pages.append((int(parts[i]), parts[i + 1]))
    return pages


def locate_in_markdown(
    md_path: Path,
    source_text: str,
    target_value: str | None = None,
    context: str | None = None,
) -> tuple[int | None, str | None]:
    if not md_path.exists():
        return None, None
    md = md_path.read_text(encoding="utf-8")
    pages = _pages_from_markdown(md)
    if not pages:
        score = _score_page_text(md, source_text, target_value, context)
        if score >= 5:
            return None, _reference_snippet(md, source_text)
        return None, None

    best_page: int | None = None
    best_score = 0
    best_ref: str | None = None
    for page_num, content in pages:
        score = _score_page_text(content, source_text, target_value, context)
        if score > best_score:
            best_score = score
            best_page = page_num
            best_ref = content
    if best_score < 4:
        return None, None
    return best_page, (best_ref[:4000] if best_ref else None)


def locate_in_pdf(
    pdf_path: Path,
    source_text: str,
    target_value: str | None = None,
    context: str | None = None,
) -> int | None:
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
            score = _score_page_text(doc[i].get_text(), source_text, target_value, context)
            if score > best_score:
                best_score = score
                best_page = i + 1
    return best_page if best_score >= 4 else None


def _comma_variants(number: str) -> list[str]:
    canonical = _canonical_number(number)
    if not canonical:
        return []
    sign = "-" if canonical.startswith("-") else ""
    unsigned = canonical.lstrip("-")
    whole, _, frac = unsigned.partition(".")
    suffix = f".{frac}" if frac else ""
    western = f"{int(whole):,}{suffix}" if whole.isdigit() else f"{whole}{suffix}"
    if len(whole) > 3:
        head = whole[:-3]
        tail = whole[-3:]
        indian_groups = []
        while len(head) > 2:
            indian_groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            indian_groups.insert(0, head)
        indian = f"{','.join(indian_groups)},{tail}{suffix}"
    else:
        indian = f"{whole}{suffix}"
    return list(dict.fromkeys([f"{sign}{canonical.lstrip('-')}", f"{sign}{western}", f"{sign}{indian}"]))


def _search_needles(source_text: str, target_value: str | None = None) -> list[str]:
    """Ordered search strings — longest / most specific first."""
    needles: list[str] = []
    seen: set[str] = set()

    def add(raw: str | None) -> None:
        if not raw:
            return
        text = re.sub(r"\s+", " ", raw).strip()
        if len(text) < 2 or text in seen:
            return
        seen.add(text)
        needles.append(text)

    for number in _target_numbers(
        source_text,
        target_value,
        include_source_numbers=not bool(target_value),
    ):
        add(number)
        for variant in _comma_variants(number):
            add(variant)
    return sorted(needles, key=len, reverse=True)


def _split_markdown_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _locate_markdown_table_cell(
    reference_text: str | None,
    source_text: str,
    target_value: str | None,
) -> tuple[int, int] | None:
    if not reference_text:
        return None

    target_numbers = _target_numbers(
        source_text,
        target_value,
        include_source_numbers=not bool(target_value),
    )
    if not target_numbers:
        return None

    source_words = set(_label_words(source_text))
    rows: list[list[str]] = []
    for line in reference_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or "---" in stripped:
            continue
        rows.append(_split_markdown_table_row(stripped))

    best: tuple[int, int, int] | None = None
    for row_index, cells in enumerate(rows):
        label = cells[0] if cells else ""
        label_words = set(re.findall(r"[a-zA-Z]{4,}", label.lower()))
        label_score = len(source_words & label_words)
        if source_words and label_score == 0:
            continue
        for cell_index, cell in enumerate(cells[1:], start=1):
            if any(_numbers_equal(cell, target) for target in target_numbers):
                score = label_score * 10 + max(0, 10 - abs(cell_index - 1))
                if best is None or score > best[2]:
                    best = (row_index, cell_index, score)

    return (best[0], best[1]) if best else None


def _pdf_page_size_points(pdf_path: Path, page: int) -> tuple[float, float] | None:
    try:
        import fitz

        with fitz.open(pdf_path) as doc:
            if page < 1 or page > doc.page_count:
                return None
            rect = doc[page - 1].rect
            return float(rect.width), float(rect.height)
    except Exception:
        pass

    if not shutil.which("pdfinfo"):
        return None
    try:
        result = subprocess.run(
            ["pdfinfo", "-f", str(page), "-l", str(page), str(pdf_path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    match = re.search(r"Page(?:\s+\d+)? size:\s+([\d.]+)\s+x\s+([\d.]+)\s+pts", result.stdout)
    if not match:
        match = re.search(r"Page size:\s+([\d.]+)\s+x\s+([\d.]+)\s+pts", result.stdout)
    if not match:
        return None
    return float(match.group(1)), float(match.group(2))


def _render_pdf_page_image(pdf_path: Path, page: int, *, dpi: int = 200):
    try:
        from PIL import Image
    except ImportError:
        return None

    try:
        import fitz

        with fitz.open(pdf_path) as doc:
            if page < 1 or page > doc.page_count:
                return None
            pix = doc[page - 1].get_pixmap(dpi=dpi, alpha=False)
            mode = "RGB" if pix.n < 4 else "RGBA"
            return Image.frombytes(mode, (pix.width, pix.height), pix.samples).convert("L")
    except Exception:
        pass

    if not shutil.which("pdftoppm"):
        return None
    try:
        with tempfile.TemporaryDirectory(prefix="capital-nerve-pdf-page-") as tmp:
            prefix = Path(tmp) / "page"
            result = subprocess.run(
                [
                    "pdftoppm",
                    "-f",
                    str(page),
                    "-l",
                    str(page),
                    "-r",
                    str(dpi),
                    "-png",
                    str(pdf_path),
                    str(prefix),
                ],
                check=False,
                capture_output=True,
                timeout=20,
            )
            if result.returncode != 0:
                return None
            image_path = Path(tmp) / f"page-{page}.png"
            if not image_path.exists():
                matches = list(Path(tmp).glob("page-*.png"))
                if not matches:
                    return None
                image_path = matches[0]
            return Image.open(image_path).convert("L")
    except (OSError, subprocess.SubprocessError):
        return None


def _group_positions(positions: list[int], *, gap: int = 3) -> list[tuple[int, int]]:
    groups: list[list[int]] = []
    for pos in positions:
        if not groups or pos > groups[-1][-1] + gap:
            groups.append([pos])
        else:
            groups[-1].append(pos)
    return [(g[0], g[-1]) for g in groups]


def _major_vertical_lines(image, *, threshold: int = 170) -> list[int]:
    width, height = image.size
    pixels = image.load()
    y0 = int(height * 0.13)
    y1 = int(height * 0.65)
    min_count = int((y1 - y0) * 0.42)
    positions: list[int] = []
    for x in range(width):
        count = sum(1 for y in range(y0, y1) if pixels[x, y] < threshold)
        if count >= min_count:
            positions.append(x)
    return [(start + end) // 2 for start, end in _group_positions(positions)]


def _text_bands(image, label_left: int, label_right: int, *, threshold: int = 150) -> list[tuple[int, int]]:
    _width, height = image.size
    pixels = image.load()
    y0 = int(height * 0.12)
    y1 = int(height * 0.72)
    positions: list[int] = []
    for y in range(y0, y1):
        count = sum(1 for x in range(label_left, label_right) if pixels[x, y] < threshold)
        if count > 8:
            positions.append(y)
    bands = _group_positions(positions)
    return [(start, end) for start, end in bands if 2 <= end - start + 1 <= 28]


def _ink_bbox_in_cell(
    image,
    *,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    threshold: int = 170,
) -> tuple[int, int, int, int] | None:
    pixels = image.load()
    width, height = image.size
    left = max(0, min(width - 1, x0 + 6))
    right = max(0, min(width, x1 - 4))
    top = max(0, min(height - 1, y0 + 1))
    bottom = max(0, min(height, y1 - 1))
    points: list[tuple[int, int]] = []
    for y in range(top, bottom):
        for x in range(left, right):
            if pixels[x, y] < threshold:
                points.append((x, y))
    if not points:
        return None
    return (
        min(x for x, _y in points),
        min(y for _x, y in points),
        max(x for x, _y in points) + 1,
        max(y for _x, y in points) + 1,
    )


def _locate_table_bbox_from_image(
    pdf_path: Path,
    source_text: str,
    page: int,
    target_value: str | None,
    reference_text: str | None,
) -> list[float] | None:
    cell = _locate_markdown_table_cell(reference_text, source_text, target_value)
    if cell is None:
        return None
    row_index, cell_index = cell

    image = _render_pdf_page_image(pdf_path, page)
    page_size = _pdf_page_size_points(pdf_path, page)
    if image is None or page_size is None:
        return None

    width, height = image.size
    lines = _major_vertical_lines(image)
    if len(lines) < 4:
        return None

    gaps = [(lines[i + 1] - lines[i], i) for i in range(len(lines) - 1)]
    label_gap_index = max(gaps, key=lambda item: item[0])[1]
    label_left = lines[max(0, label_gap_index - 1)] if label_gap_index > 0 else lines[0]
    label_right = lines[label_gap_index + 1]
    value_edges = lines[label_gap_index + 1 :]
    if len(value_edges) <= cell_index:
        return None

    bands = _text_bands(image, label_left, label_right)
    if not bands:
        return None

    band_index = row_index
    if row_index > 0 and bands and bands[0][1] - bands[0][0] < 20:
        # Multi-line table headers usually consume an extra detected text band.
        band_index += 1
    if band_index >= len(bands):
        return None

    centers = [(start + end) / 2 for start, end in bands]
    center = centers[band_index]
    prev_center = centers[band_index - 1] if band_index > 0 else bands[band_index][0] - 18
    next_center = centers[band_index + 1] if band_index + 1 < len(centers) else bands[band_index][1] + 18
    y0 = int((prev_center + center) / 2)
    y1 = int((center + next_center) / 2)
    x0 = value_edges[cell_index - 1]
    x1 = value_edges[cell_index]

    ink = _ink_bbox_in_cell(image, x0=x0, y0=y0, x1=x1, y1=y1)
    if ink is None:
        return None

    ix0, iy0, ix1, iy1 = ink
    page_width, page_height = page_size
    scale_x = page_width / width
    scale_y = page_height / height
    pad_x = 2 * scale_x
    pad_y = 2 * scale_y
    return [
        max(0.0, ix0 * scale_x - pad_x),
        max(0.0, iy0 * scale_y - pad_y),
        min(page_width, ix1 * scale_x + pad_x),
        min(page_height, iy1 * scale_y + pad_y),
    ]


def locate_bbox_in_pdf(
    pdf_path: Path,
    source_text: str,
    page: int,
    target_value: str | None = None,
    reference_text: str | None = None,
) -> list[float] | None:
    """Return [x0, y0, x1, y1] for the target value on ``page`` in PDF points."""
    try:
        import fitz
    except ImportError:
        return _locate_table_bbox_from_image(
            pdf_path,
            source_text,
            page,
            target_value,
            reference_text,
        )

    if not pdf_path.exists() or page < 1:
        return None

    with fitz.open(pdf_path) as doc:
        if page > doc.page_count:
            return None
        page_obj = doc[page - 1]
        label = _source_label_for_match(source_text)
        label_words = _label_words(source_text)
        label_hits = page_obj.search_for(label) if label and len(label) >= 4 else []

        candidates: list = []
        for needle in _search_needles(source_text, target_value):
            candidates.extend(page_obj.search_for(needle))

        if not candidates:
            targets = _target_numbers(
                source_text,
                target_value,
                include_source_numbers=not bool(target_value),
            )
            for word in page_obj.get_text("words"):
                word_text = str(word[4])
                if any(_numbers_equal(word_text, target) for target in targets):
                    candidates.append(fitz.Rect(word[0], word[1], word[2], word[3]))

        if not candidates:
            return _locate_table_bbox_from_image(
                pdf_path,
                source_text,
                page,
                target_value,
                reference_text,
            )

        def score_rect(rect) -> float:
            score = 0.0
            if label_hits:
                best_label = min(label_hits, key=lambda r: abs(r.y0 - rect.y0))
                y_distance = abs(best_label.y0 - rect.y0)
                score += max(0.0, 100.0 - y_distance)
                if best_label.x0 < rect.x0:
                    score += 20.0
            if label_words:
                line_text = page_obj.get_textbox(
                    fitz.Rect(
                        0,
                        max(0, rect.y0 - 4),
                        page_obj.rect.x1,
                        min(page_obj.rect.y1, rect.y1 + 4),
                    )
                ).lower()
                score += sum(5.0 for word in label_words if word in line_text)
            return score

        best = max(candidates, key=score_rect)
        return [best.x0, best.y0, best.x1, best.y1]
    return None


def locate_source(
    *,
    parsed_md_path: Path,
    pdf_path: Path,
    source_text: str,
    target_value: str | None = None,
    context: str | None = None,
    preferred_page: int | None = None,
) -> dict[str, int | str | list[float] | None]:
    page, reference_text = locate_in_markdown(parsed_md_path, source_text, target_value, context)
    if page is None:
        page = locate_in_pdf(pdf_path, source_text, target_value, context)

    if preferred_page is not None and preferred_page > 0:
        page = preferred_page
        if parsed_md_path.exists():
            page_ref = _page_content_from_markdown(
                parsed_md_path.read_text(encoding="utf-8"),
                preferred_page,
            )
            if page_ref:
                reference_text = page_ref

    bbox = (
        locate_bbox_in_pdf(pdf_path, source_text, page, target_value, reference_text)
        if page
        else None
    )
    return {
        "page": page,
        "reference_text": reference_text,
        "bbox": bbox,
    }
