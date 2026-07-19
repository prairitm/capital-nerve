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
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_fact_review_decisions_status
    ON fact_review_decisions(decision, updated_at DESC);

CREATE INDEX IF NOT EXISTS ix_fact_review_decisions_reviewer
    ON fact_review_decisions(reviewed_by, updated_at DESC);
