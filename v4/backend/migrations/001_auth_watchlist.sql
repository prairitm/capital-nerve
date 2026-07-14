CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL COLLATE NOCASE UNIQUE,
    full_name TEXT,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('MEMBER', 'ADMIN')) DEFAULT 'MEMBER',
    is_active INTEGER NOT NULL CHECK (is_active IN (0, 1)) DEFAULT 1,
    must_change_password INTEGER NOT NULL CHECK (must_change_password IN (0, 1)) DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_login_at TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS ix_sessions_expires_at ON sessions(expires_at);

CREATE TABLE IF NOT EXISTS watchlist_companies (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    company_id TEXT NOT NULL,
    added_at TEXT NOT NULL,
    PRIMARY KEY (user_id, company_id)
);

CREATE INDEX IF NOT EXISTS ix_watchlist_user_added
    ON watchlist_companies(user_id, added_at DESC);
