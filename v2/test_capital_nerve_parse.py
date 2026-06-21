"""Tests for PDF parse validation helpers."""

from __future__ import annotations

from capital_nerve_parse import has_summary_filler, validate_parsed_markdown


def test_has_summary_filler_detects_placeholder():
    md = "Overall notes and further financial statements continue in similar structured tables."
    assert has_summary_filler(md)


def test_has_summary_filler_clean_markdown():
    md = "## Unaudited Consolidated Financial Results\n| TOTAL INCOME | 40,898.41 |"
    assert not has_summary_filler(md)


def test_validate_flags_short_markdown(tmp_path):
    pdf = tmp_path / "tiny.pdf"
    md_path = tmp_path / "out.md"
    # Minimal PDF with pymupdf
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "UNAUDITED CONSOLIDATED FINANCIAL RESULTS FOR THE QUARTER")
    page.insert_text((72, 100), "3. TOTAL INCOME 40,898.41")
    page.insert_text((72, 130), "UNAUDITED STANDALONE FINANCIAL RESULTS FOR THE QUARTER")
    page.insert_text((72, 160), "3. TOTAL INCOME 38,500.06")
    doc.save(pdf)
    doc.close()

    md_path.write_text("# Only standalone\n| TOTAL INCOME | 38,500 |", encoding="utf-8")
    issues = validate_parsed_markdown(md_path.read_text(encoding="utf-8"), pdf)
    assert "missing_consolidated_section" in issues
