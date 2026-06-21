# services/pipeline/orderbook

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Stage 1e. Regex extractor for order-book disclosures in investor
presentations, concall transcripts, financial results, and annual reports.
Outputs feed `order_book_growth_yoy`, `book_to_bill`,
`order_book_to_revenue`, `order_concentration_pct`, and
`order_cancellation_rate` plus their downstream signals.

## Source

- Path: `backend/app/services/pipeline/orderbook.py`
- Layer: backend-service

## Contract

- `is_order_book_document(document) -> bool` — gate.
- `run_order_book_extraction(db, *, document, event) -> int` — rows written.
- Codes produced (must exist in `financial_line_item_definitions`):
  `opening_order_book`, `closing_order_book`, `order_inflow`,
  `executed_orders`, `cancelled_orders`, `top_customer_orders`.

## Dependencies

- May import: `app.models.{events,facts}`, `app.db.enums`.
- Must not import: LLM modules.

## Patterns (symmetry)

- Output is `ExtractedValue` rows in `crore`. The metric engine reads them
  through the same `InputResolver` path as financial line items.
- Numbers are parsed with the standard "Rs N Cr" / "N crore" tail; commas
  are stripped before `float()`.

## Verification checklist

- [ ] Re-runs do not duplicate rows.
- [ ] Each row carries `unit="crore"`, `confidence_level=MEDIUM`.
- [ ] Documents without any order-book phrasing return 0, no crash.
