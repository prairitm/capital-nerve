ALTER TABLE fact_review_decisions
    ADD COLUMN application_status TEXT NOT NULL DEFAULT 'not_applicable'
    CHECK (application_status IN ('pending', 'applied', 'failed', 'not_applicable'));

ALTER TABLE fact_review_decisions ADD COLUMN applied_at TEXT;
ALTER TABLE fact_review_decisions ADD COLUMN applied_by TEXT;
ALTER TABLE fact_review_decisions ADD COLUMN application_error TEXT;

ALTER TABLE fact_review_decisions
    ADD COLUMN recompute_status TEXT NOT NULL DEFAULT 'not_applicable'
    CHECK (recompute_status IN ('pending', 'succeeded', 'failed', 'not_applicable'));

ALTER TABLE fact_review_decisions ADD COLUMN recomputed_at TEXT;
ALTER TABLE fact_review_decisions ADD COLUMN recompute_error TEXT;

UPDATE fact_review_decisions
SET application_status = CASE
        WHEN decision = 'approved' THEN 'pending'
        ELSE 'not_applicable'
    END,
    recompute_status = 'not_applicable';

CREATE INDEX IF NOT EXISTS ix_fact_review_decisions_application
    ON fact_review_decisions(application_status, updated_at);
