-- DealHunter SQLite schema
-- Covers §3.2: deduplication, historical tracking, active deals + coupons
-- §3.1 sources: slickdeals_rss, walmart, target, aldi, coupon aggregators
-- §3.3 alerts deduped via alerts.deal_hash
-- §3.4 categories: electronics, groceries, cleaning, personal_care

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS deals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deal_hash TEXT NOT NULL UNIQUE,          -- sha256(title|store|url) for dedup
    title TEXT NOT NULL,
    store TEXT NOT NULL,                     -- Walmart | Target | Aldi | Slickdeals | ...
    category TEXT NOT NULL                   -- electronics | groceries | cleaning | personal_care | apparel | home_tools
        CHECK (category IN ('electronics','groceries','cleaning','personal_care','apparel','home_tools')),
    price REAL,
    original_price REAL,
    discount_pct REAL,                       -- computed; alert threshold >20% or historical low
    unit_price REAL,                         -- §3.2 price-per-unit normalization
    unit TEXT,                               -- e.g. 'oz', 'lb', 'sheet', 'pod', 'count'
    url TEXT NOT NULL,
    image_url TEXT,
    source TEXT NOT NULL DEFAULT 'slickdeals_rss',
    is_active INTEGER NOT NULL DEFAULT 1,
    is_historical_low INTEGER NOT NULL DEFAULT 0,
    coupon_available INTEGER NOT NULL DEFAULT 0,  -- badge for dashboard
    first_seen TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    scope TEXT NOT NULL DEFAULT 'unknown' -- local (near ZIP) | online | unknown
);
CREATE INDEX IF NOT EXISTS idx_deals_category ON deals(category);
CREATE INDEX IF NOT EXISTS idx_deals_store ON deals(store);
CREATE INDEX IF NOT EXISTS idx_deals_active ON deals(is_active);
CREATE INDEX IF NOT EXISTS idx_deals_last_seen ON deals(last_seen);

CREATE TABLE IF NOT EXISTS coupons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    store TEXT NOT NULL,
    code TEXT,
    description TEXT,
    promo_link TEXT,
    deal_hash TEXT,                          -- optional FK to deals.deal_hash
    source TEXT NOT NULL DEFAULT 'store_feed', -- retailmenot | honey | store_feed
    is_active INTEGER NOT NULL DEFAULT 1,
    expires_at TIMESTAMP,
    discovered_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(store, code),
    FOREIGN KEY (deal_hash) REFERENCES deals(deal_hash) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_coupons_store ON coupons(store);
CREATE INDEX IF NOT EXISTS idx_coupons_deal ON coupons(deal_hash);
CREATE INDEX IF NOT EXISTS idx_coupons_active ON coupons(is_active);

CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deal_hash TEXT NOT NULL,
    price REAL NOT NULL,
    original_price REAL,
    checked_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (deal_hash) REFERENCES deals(deal_hash) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_price_history_hash ON price_history(deal_hash);
CREATE INDEX IF NOT EXISTS idx_price_history_checked ON price_history(checked_at);

-- §3.2 watchlist matching: keyword + synonyms JSON array, per-category threshold
CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL UNIQUE,            -- e.g. 'laptop', 'dish detergent'
    synonyms TEXT NOT NULL DEFAULT '[]',     -- JSON array string
    category TEXT,                           -- nullable = match any category
    min_discount_pct REAL NOT NULL DEFAULT 20.0,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- §3.3 prevent duplicate Telegram alerts
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deal_hash TEXT NOT NULL,
    coupon_id INTEGER,
    channel TEXT NOT NULL DEFAULT 'telegram',
    message TEXT,
    sent_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(deal_hash, channel),
    FOREIGN KEY (deal_hash) REFERENCES deals(deal_hash) ON DELETE CASCADE,
    FOREIGN KEY (coupon_id) REFERENCES coupons(id) ON DELETE SET NULL
);

-- §3.4 live feature: last scrape timestamps per source
CREATE TABLE IF NOT EXISTS scrape_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP,
    items_found INTEGER NOT NULL DEFAULT 0,
    items_matched INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running','success','error')),
    error_msg TEXT
);
CREATE INDEX IF NOT EXISTS idx_scrape_runs_source ON scrape_runs(source);

-- User-editable settings (zip code, etc.), surfaced in dashboard + API
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
