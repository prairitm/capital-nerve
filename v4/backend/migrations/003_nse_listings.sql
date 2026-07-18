CREATE TABLE IF NOT EXISTS nse_listings (
    symbol TEXT PRIMARY KEY COLLATE NOCASE,
    company_name TEXT NOT NULL,
    series TEXT,
    listing_date TEXT,
    isin TEXT,
    is_active INTEGER NOT NULL CHECK (is_active IN (0, 1)) DEFAULT 1,
    refreshed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_nse_listings_company_name
    ON nse_listings(company_name COLLATE NOCASE);

CREATE INDEX IF NOT EXISTS ix_nse_listings_active_symbol
    ON nse_listings(is_active, symbol COLLATE NOCASE);
