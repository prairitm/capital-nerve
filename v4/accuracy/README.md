# Capital Nerve Accuracy Contract v0.1

This directory defines what "accurate" means before extraction logic is changed.
The contract deliberately separates **precision** (published facts must be right)
from **coverage** (how many facts the system can safely publish).

## Initial scope

Version 0.1 covers financial-result documents and these decision-critical facts:

- `revenue_from_operations`
- `other_income`
- `total_income`
- `finance_cost`
- `depreciation_and_amortization`
- `total_expenses`
- `pbt`
- `tax_expense`
- `pat`
- `eps_basic`
- `eps_diluted`

Investor presentations and earnings-call transcripts enter the benchmark only
after the financial-result gate passes. Their dimensions and language make them
a separate evaluation problem.

## Unit of evaluation

One gold record represents one expected fact in one document. A fact is not
correct unless every required field is correct:

1. `fact_code`
2. numeric value or text value
3. `unit`
4. `period_end`
5. `period_type`
6. `basis` (`consolidated` or `standalone`)
7. `source_page`
8. `source_text` that visibly supports the value

Company and document IDs identify the source. Optional dimensions are part of
the identity whenever present.

## Numeric comparison

Gold values are stored exactly as displayed in the source after parsing Indian
number formatting and accounting negatives. The evaluator may use only these
tolerances:

| Value type | Absolute tolerance |
| --- | ---: |
| currency in crore | 0.01 |
| EPS in rupees | 0.01 |
| percentage | 0.01 percentage points |
| count or shares | 0 |

Unit conversion is explicit. A numerically equivalent value with the wrong or
missing unit is not correct.

## Evidence rules

- Page numbering is 1-based and refers to the PDF page.
- `source_text` must contain the row label and displayed value.
- Evidence from a different period, basis, or table is incorrect.
- A fact without page evidence cannot be auto-published.
- Derived facts must name their input fact IDs instead of pretending to have a
  source page.

## Release gates

The benchmark reports precision and coverage separately. The product may call
the auto-published subset "perfect" only when all of these gates pass:

| Gate | Required result |
| --- | ---: |
| Auto-published critical-fact precision | 100% |
| Wrong-period errors | 0 |
| Wrong-basis errors | 0 |
| Wrong-unit errors | 0 |
| Published facts without valid page evidence | 0 |
| Unresolved conflicting observations auto-published | 0 |
| Benchmark regression versus accepted baseline | 0 |

Coverage is not allowed to lower precision. When the system cannot prove a
fact, it must abstain and send the item to review. The scorecard always reports:

- auto-published precision
- auto-published coverage
- review rate
- abstention rate
- per-fact precision and recall
- errors by company, document layout, period, and basis

## Benchmark-30 construction

The first benchmark contains 30 documents:

- at least 10 companies
- at least 8 quarterly, 8 half-year, and 8 annual result documents
- both consolidated and standalone statements
- at least 5 difficult PDFs (scanned, rotated, multi-table, or poor text layer)
- no more than 4 documents from one company

Use 20 documents for development and keep 10 locked as a holdout set. Never
change a gold label to make a model prediction pass. Every gold record requires
independent review by a second person before it becomes `approved`.

## Current checkpoint

Step 11 has seven draft-labeled development documents: TCS Q1 FY27, Reliance Q1
FY26, L&T Q2 FY26, KEC FY2024, Reliance H1 FY26, L&T nine months FY26, and
KEC nine months FY25. Together they contain 150 visually verified facts across
four issuer layouts, quarter, half-year, nine-month and annual periods, and both
consolidated and standalone bases. Deterministic replay currently scores
150/150 for 100% provisional precision, coverage, and recall. The KEC
nine-month filing is the first difficult-PDF case: a 17 MB scanned paper-capture
document whose OCR merges period headings and drops the standalone table title.
The parser now excludes title cells from period-section expansion and uses
same-page post-table evidence to recover statement basis without leaking across
PDF page boundaries. It also selects cumulative columns, prefers final
post-exceptional reconciliations on the same statement page, and preserves basis
across continuation tables. Equal-confidence disagreements route to review;
incomplete source evidence routes to review; and facts without any source
evidence abstain. This is not a release result until a second reviewer approves
the gold labels.

Review-required and abstained facts now enter an administrator-only operational
queue. Consolidated and standalone observations retain separate resolution
identities, only facts with status `resolved` can feed metrics or signals, and
administrator decisions are stored as an audited application-database overlay.
Queue approval does not auto-publish or write to the read-only analytics
database. A separate dry-run-first maintenance command now validates approved
decisions, blocks stale or evidence-incomplete candidates, promotes each fact
in an analytics transaction, records immutable before/after state, and reruns
metrics and signals once per affected event. Its idempotent ledger allows an
interrupted app-database status update or downstream recomputation to be safely
resumed.

## Development checkpoint v0.2

The development set now contains 20 pipeline documents from 14 companies: 19
positive-label documents plus one zero-positive multi-issuer newspaper control.
There are 428 schema-valid draft labels and 14 difficult PDFs; no company
contributes more than two documents. The aggregate after-fix replay publishes
262 facts correctly, routes 83 to review, and abstains on 83, for 100%
provisional published precision and 61.21% coverage/recall. It has zero spurious publications and
zero evidence-page, period, period-type, basis, unit, or conflict errors.

This is not a release result. All 428 labels remain draft. The locked holdout
manifest reserves ten untouched companies/layouts, but an independent labeler
must retrieve those documents, create separate labels, and approve them before
the explicit release evaluator will run. The development reports, execution
record, error taxonomy, and review-workflow evidence are under `reports/`.

## Gold-label workflow

1. Copy `gold.example.jsonl` to a company/document-specific JSONL file.
2. Label values directly from the PDF, including page, period, basis, and unit.
3. Set `label_status` to `draft` while labeling.
4. A second reviewer checks the PDF and changes it to `approved`.
5. Only approved labels are included in release-gate scores.
6. Record corrections in version control; do not overwrite their history.

`gold.schema.json` is the machine-readable format contract. Predictions use the
same identity and fact fields, plus:

- `decision`: `publish`, `review`, or `abstain`
- `confidence`: optional model confidence (reported, never trusted as truth)
- `extraction_method`: parser or model that produced the observation
- `has_unresolved_conflict`: must be false before publication

Every prediction must carry the gold record's `label_id`. Missing predictions
count as abstentions; unknown published IDs count as false positives.

Run the evaluator with:

```bash
python accuracy/evaluate.py \
  --gold accuracy/gold.example.jsonl \
  --predictions accuracy/predictions.example.jsonl
```

Only `approved` gold records are scored. The command exits with status `1` when
a release gate fails and status `2` for malformed or ambiguous inputs, making
it suitable for CI. Add `--require-gates` in CI. The example label is
intentionally `draft`, so it is ignored and does not pass the release gate.

To diagnose the current SQLite baseline before independent review is complete:

```bash
python accuracy/baseline_from_db.py \
  --database data/capital_nerve.db \
  --gold accuracy/gold/tcs_2026_q1.jsonl \
  --output accuracy/reports/tcs_2026_q1_predictions.jsonl

python accuracy/evaluate.py \
  --gold accuracy/gold/tcs_2026_q1.jsonl \
  --predictions accuracy/reports/tcs_2026_q1_predictions.jsonl \
  --include-draft \
  --output accuracy/reports/tcs_2026_q1_baseline.json
```

Reports created with `--include-draft` are explicitly provisional and can never
pass release gates.

To replay the deterministic parser against cached Markdown after a code change:

```bash
python accuracy/replay_deterministic.py \
  --gold accuracy/gold/tcs_2026_q1.jsonl \
  --output accuracy/reports/tcs_2026_q1_after_fix_predictions.jsonl

python accuracy/evaluate.py \
  --gold accuracy/gold/tcs_2026_q1.jsonl \
  --predictions accuracy/reports/tcs_2026_q1_after_fix_predictions.jsonl \
  --include-draft \
  --output accuracy/reports/tcs_2026_q1_after_fix.json
```
