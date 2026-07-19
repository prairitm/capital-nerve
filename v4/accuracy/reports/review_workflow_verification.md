# Review workflow verification

The exercise used only the isolated benchmark analytics database and a temporary application database.

## Genuine pipeline item

HINDUNILVR consolidated `finance_cost` for 2025-06-30 entered `review_required` with value 80 crore and LLM source text `Finance costs 80`. The candidate had no `source_page`. It appeared in the administrator queue; the isolated queue contained 374 open/decided items at the time of the check. The same event had zero `finance_cost` rows in `extracted_values`, zero metrics, and zero signals, confirming that withheld facts were not consumed downstream.

An administrator approval was recorded in the temporary app overlay and reconciliation preview was run. Preview remained read-only and returned `invalid`: “The approved observation lacks page-level evidence and cannot be published.” No analytics fact was promoted. This is the required safe behavior, but it also means the genuine item cannot honestly exercise apply without inventing page metadata. The blocker is retained rather than bypassed.

## Valid-candidate transaction fixture

`microservices.test_review_reconciliation` exercises the remainder of the workflow against temporary databases containing a page-supported candidate:

1. preview makes no analytics write;
2. apply promotes the selected observation and records immutable before/after state;
3. metrics/signals recomputation is called once per event;
4. a second run is idempotent and does not duplicate the fact;
5. an interrupted application-status update resumes without reapplying the fact;
6. failed recomputation is resumable; and
7. stale or page-incomplete candidates are blocked.

Thus the transactional machinery is verified, while the actual new-document approval stops at the evidence gate exactly as required. A future parser run must produce a page-supported observation before that genuine item can be applied.
