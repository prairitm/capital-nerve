# Development pipeline execution record

## Architecture and isolated execution

`microservices/run.py` carries one parameter envelope through seven HTTP steps: company identity (`/companies`), NSE announcement discovery (`/events/discover`), event/document resolution (`/event-type/resolve`), document ingestion and fact extraction (`/values/extract`), metric computation (`/metrics/compute`), signal evaluation (`/signals/evaluate`), and alert retrieval (`/alerts`). The document queue must survive steps 1 and 2 so manual URL and local-file fallbacks reach step 3.

The benchmark used localhost ports 8120–8126 and a temporary root outside the repository. Every service-specific database environment variable (`COMPANY_SERVICE_DB_PATH`, `EVENT_SERVICE_DB_PATH`, `EVENT_TYPE_SERVICE_DB_PATH`, `VALUES_SERVICE_DB_PATH`, `METRICS_SERVICE_DB_PATH`, `SIGNALS_SERVICE_DB_PATH`, and `ALERTS_SERVICE_DB_PATH`) pointed to one isolated SQLite database. `COMPANY_SERVICE_DOCUMENTS_DIR`, `EVENT_SERVICE_DOCUMENTS_DIR`, `VALUES_SERVICE_DOCUMENTS_DIR`, and `VALUES_SERVICE_PARSED_DIR` pointed to temporary document and Markdown directories. No production/user database was opened for writes, and PDFs, Markdown caches, logs, and the benchmark database are not repository artifacts.

Documents are represented in `documents`; parsed Markdown is an external cache keyed by document SHA; raw evidence is stored in `fact_observations`; reconciliation decisions are stored in `resolved_facts`; only resolved observations are copied into `extracted_values` for metrics and signals. The review overlay lives in the separate application database.

The frozen financial-result contract contains 11 comparable facts: revenue from operations, other income, total income, finance cost, depreciation/amortization, total expenses, PBT, tax expense, PAT, basic EPS, and diluted EPS. It supports statement bases `consolidated` and `standalone`, and period types `quarter`, `half_year`, `nine_months`, and `year`. Value, normalized unit, period end/type, basis, one-based PDF page, and supporting row text are all correctness fields. The contract does not currently model continuing-versus-discontinued operation scope, so ambiguous tax rows are withheld.

## First command

```bash
python microservices/run.py \
  --symbol INFY \
  --from-date 20-07-2025 \
  --to-date 25-07-2025 \
  --event-type "Financial Results" \
  --document "document_type=financial_result,source_mode=manual_url,source_url=https://nsearchives.nseindia.com/corporate/Infosys_24072025193340_Financialsnewspaperad_24072025.pdf" \
  --values-sync \
  --company-url http://127.0.0.1:8120 \
  --event-url http://127.0.0.1:8121 \
  --event-type-url http://127.0.0.1:8122 \
  --values-url http://127.0.0.1:8123 \
  --metrics-url http://127.0.0.1:8124 \
  --signals-url http://127.0.0.1:8125 \
  --alerts-url http://127.0.0.1:8126
```

## Execution outcome

The expanded development inventory has 20 pipeline documents, 14 companies, 19 positive-label documents, one zero-positive multi-issuer newspaper control, and 428 draft facts. Fourteen documents meet the inventory's difficult-PDF criteria. No company contributes more than two documents.

All newly selected documents went through the real seven-step flow. Detailed URLs, event IDs, SHAs, dates, difficulty tags, observation counts, resolved counts, publish/review counts, and errors are frozen in `benchmark_inventory.json`. The most important exceptional outcomes were:

- Infosys April 2025: `nse_auto` found seven announcements but event-type validation returned no valid result PDF; supported manual-URL fallback retrieved the board outcome. Its 380-page scanned package then exceeded the 900-second values timeout. Forty independently labeled facts remain in the benchmark as explicit abstentions.
- Sun Pharma newspaper: the issuer's result was available only through a QR code while unrelated issuers had full tables. Baseline extraction published seven unrelated facts; the multi-issuer guard now publishes zero.
- Bharti Airtel: the 82-page scanned filing completed in 494 seconds with 83 observations, 29 resolved/published candidates, and 54 review-required candidates.
- ITC annual: the filing completed with 112 observations, 37 resolved/published candidates, and 75 review-required candidates; quarter and annual columns share the same period end.

All source PDFs and renderings remain in the isolated temporary data root and are intentionally uncommitted.
