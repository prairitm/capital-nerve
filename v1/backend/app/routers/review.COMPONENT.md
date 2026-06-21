# routers/review

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Admin review queue list and update.

## Source

- Path: `backend/app/routers/review.py`
- Prefix: `/review`
- Tags: `["review"]`
- Layer: backend-router (admin)

## Endpoints

- `GET /review?status_filter=` — admin-only (uses `get_current_admin`). Returns up to 100 rows joined with `Company`, `SourceDocument`, and the latest `ExtractionJob` per document. Each row includes `pipeline_stages`, `signal_diagnostics` (fired / not-fired rules with reasons), `publish_blocked_reasons`, and `auto_publish_threshold`.
- `GET /review/{review_id}/pipeline` — admin-only drill-down for one queue row: latest job metadata, period, `extracted_values`, `financial_statement_facts`, `calculated_metrics`, `generated_signals`, `intelligence_cards`, and `signal_diagnostics`.
- `PATCH /review/{review_id}` — body `UpdateReview { status?, issue_description? }`. Sets `resolved_at` when the new status is `APPROVED`, `REJECTED`, `CORRECTED`, or `RESOLVED`.
  - On **APPROVED**: publishes the ingestion artifacts — flips
    `is_published=True` on the linked `CompanyEvent`, every `GeneratedSignal`,
    and every `IntelligenceCard` tied to the same `document_id`. This is the
    manual mirror of the auto-publish gate in
    [`services/pipeline/runner.py`](../services/pipeline/runner.py).
  - On **REJECTED**: retracts those same rows back to `is_published=False`, including
    jobs that were already auto-published (`RESOLVED` queue status). Updates the
    latest `ExtractionJob.meta['published']` to `false` so the list UI stays accurate.

## Dependencies

- Imports: `fastapi`, `pydantic.BaseModel`, `sqlalchemy.select` / `update`,
  `app.core.deps.get_current_admin`, models (`ReviewQueue`, `Company`,
  `SourceDocument`, `CompanyEvent`, `GeneratedSignal`, `IntelligenceCard`,
  `AppUser`).

## Patterns (symmetry)

- Admin gating uses `get_current_admin` dependency, not an inline `user.user_type` check.
- Terminal statuses (`APPROVED`, `REJECTED`, `CORRECTED`, `RESOLVED`) trigger
  `resolved_at = datetime.now(timezone.utc)` — keep this set aligned with the
  frontend admin buttons.
- The publish / retract helpers mirror what the pipeline runner does on
  high-confidence completion. If you change one, change the other so the
  manual-approval and auto-publish code paths stay symmetric.
- 404 when the review item is missing. No 403 — `get_current_admin` already returned 403 to non-admins.

## Verification checklist

- [ ] Both endpoints depend on `get_current_admin`
- [ ] Terminal status transitions set `resolved_at`
- [ ] Approving a review row publishes the matching event + signals + cards
- [ ] Rejecting a review row retracts (un-publishes) those same rows
- [ ] Frontend admin allow-list (`APPROVED`, `REJECTED`) matches what the route accepts
- [ ] 404 returned for missing review items
