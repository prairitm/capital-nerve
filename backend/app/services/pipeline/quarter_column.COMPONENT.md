# services/pipeline/quarter_column

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Ensure `ExtractedLineItem` values come from the **Quarter Ended** column only —
never Nine Months Ended, Year Ended, or YTD cumulative columns in Indian result PDFs.

## Source

- Path: `backend/app/services/pipeline/quarter_column.py`
- Layer: backend-service

## Contract

- `extract_quarter_ended_items(pages) -> list[ExtractedLineItem]` — stacked
  `Quarter Ended` / `Nine Months Ended` blocks plus inline highlight tables.
- `enforce_quarter_ended_only(items, pages) -> list[ExtractedLineItem]` — merges
  provider output with quarter-column parses; drops cumulative-section picks.

## Dependencies

- May import: `app.services.pipeline.llm` (`ExtractedLineItem`, `_LABEL_PATTERNS`,
  `_NUMBER_RE`, `_source_quote`).
- Called from `llm._finalize_quarter_items` after mock and LLM extraction.

## Verification checklist

- [ ] Stacked BSE/NSE page maps `Revenue from Operations` to the quarter column
      (not the nine-month block).
- [ ] Inline `Gross Revenue 283,548 … 1,071,174` row uses column 0 (current quarter).
- [ ] QoQ row `EBITDA 48,003 50,932 5.7 6.1%` uses column 1 when column 3 is a %.
