CREATE TABLE IF NOT EXISTS company_poll_state (
    company_id TEXT PRIMARY KEY,
    baseline_at TEXT NOT NULL,
    last_success_at TEXT,
    next_poll_at TEXT NOT NULL,
    lease_until TEXT,
    last_error TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_company_poll_due
    ON company_poll_state(next_poll_at, lease_until);

CREATE TABLE IF NOT EXISTS pipeline_jobs (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    canonical_event_id TEXT NOT NULL,
    pipeline_version TEXT NOT NULL,
    company_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    event_type TEXT NOT NULL,
    source_url TEXT NOT NULL,
    title TEXT,
    published_at TEXT NOT NULL,
    from_date TEXT NOT NULL,
    to_date TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    available_at TEXT NOT NULL,
    lease_until TEXT,
    worker_id TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE(canonical_event_id, pipeline_version)
);

CREATE INDEX IF NOT EXISTS ix_pipeline_jobs_claim
    ON pipeline_jobs(status, available_at, lease_until);

INSERT OR IGNORE INTO company_poll_state (
    company_id, baseline_at, next_poll_at, created_at, updated_at
)
SELECT DISTINCT company_id, datetime('now'), datetime('now'), datetime('now'), datetime('now')
FROM watchlist_companies;
