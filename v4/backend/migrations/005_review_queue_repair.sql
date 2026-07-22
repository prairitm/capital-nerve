-- Historical migration-number collisions skipped the review queue on fresh
-- installs and its reconciliation fields on deployed databases. The runtime
-- repair in app_db.py adds any absent columns to pre-existing tables.
CREATE TABLE IF NOT EXISTS fact_review_decisions (
    resolved_fact_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    fact_code TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('approved', 'rejected')),
    selected_observation_id TEXT,
    reviewer_note TEXT,
    reviewed_by TEXT NOT NULL REFERENCES users(id),
    reviewed_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    application_status TEXT NOT NULL DEFAULT 'not_applicable'
        CHECK (application_status IN ('pending', 'applied', 'failed', 'not_applicable')),
    applied_at TEXT,
    applied_by TEXT,
    application_error TEXT,
    recompute_status TEXT NOT NULL DEFAULT 'not_applicable'
        CHECK (recompute_status IN ('pending', 'succeeded', 'failed', 'not_applicable')),
    recomputed_at TEXT,
    recompute_error TEXT
);

CREATE INDEX IF NOT EXISTS ix_fact_review_decisions_status
    ON fact_review_decisions(decision, updated_at DESC);
CREATE INDEX IF NOT EXISTS ix_fact_review_decisions_reviewer
    ON fact_review_decisions(reviewed_by, updated_at DESC);
