CREATE TABLE IF NOT EXISTS notification_preferences (
    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    notification_email TEXT COLLATE NOCASE,
    email_verified_at TEXT,
    email_enabled INTEGER NOT NULL CHECK (email_enabled IN (0, 1)) DEFAULT 0,
    financial_results_enabled INTEGER NOT NULL CHECK (financial_results_enabled IN (0, 1)) DEFAULT 1,
    investor_presentations_enabled INTEGER NOT NULL CHECK (investor_presentations_enabled IN (0, 1)) DEFAULT 1,
    earnings_calls_enabled INTEGER NOT NULL CHECK (earnings_calls_enabled IN (0, 1)) DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notification_action_tokens (
    id TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL UNIQUE,
    action TEXT NOT NULL CHECK (action IN ('verify_email', 'unsubscribe')),
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    email TEXT COLLATE NOCASE,
    expires_at TEXT,
    used_at TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_notification_tokens_lookup
    ON notification_action_tokens(token_hash, action, used_at, expires_at);

CREATE TABLE IF NOT EXISTS email_outbox (
    id TEXT PRIMARY KEY,
    message_kind TEXT NOT NULL CHECK (message_kind IN ('watchlist_update', 'verify_email', 'test_email')),
    dedupe_key TEXT NOT NULL UNIQUE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    recipient_email TEXT NOT NULL COLLATE NOCASE,
    company_id TEXT,
    event_id TEXT,
    pipeline_job_id TEXT REFERENCES pipeline_jobs(id) ON DELETE SET NULL,
    action_token TEXT,
    status TEXT NOT NULL CHECK (status IN ('pending', 'sending', 'sent', 'failed', 'cancelled')) DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    available_at TEXT NOT NULL,
    lease_until TEXT,
    worker_id TEXT,
    provider_message_id TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    sent_at TEXT
);

CREATE INDEX IF NOT EXISTS ix_email_outbox_claim
    ON email_outbox(status, available_at, lease_until);
CREATE INDEX IF NOT EXISTS ix_email_outbox_user
    ON email_outbox(user_id, created_at DESC);
