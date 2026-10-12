"""SQLite init + helpers (stdlib sqlite3 per §5). WAL mode, FK enforcement."""
import sqlite3
from pathlib import Path
from . import config

def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else config.DATABASE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

def init_db(db_path: Path | None = None) -> Path:
    """Create tables from schema.sql and seed watchlist. Idempotent."""
    import json
    path = Path(db_path) if db_path else config.DATABASE_PATH
    schema = config.SCHEMA_PATH.read_text(encoding="utf-8")
    with get_connection(path) as conn:
        conn.executescript(schema)
        # Migration for DBs created before the scope column existed.
        try:
            conn.execute("ALTER TABLE deals ADD COLUMN scope TEXT NOT NULL DEFAULT 'unknown'")
        except sqlite3.OperationalError:
            pass  # column already present
        # Migration for DBs created before the 'apparel' category existed
        # (SQLite CHECK constraints can't be ALTERed — rebuild the table).
        deal_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name='deals'").fetchone()[0]
        for missing, cats in (("'apparel'", "'electronics','groceries','cleaning','personal_care','apparel'"),
                              ("'home_tools'", "'electronics','groceries','cleaning','personal_care','apparel','home_tools'")):
            deal_sql = conn.execute(
                "SELECT sql FROM sqlite_master WHERE name='deals'").fetchone()[0]
            if missing in deal_sql:
                continue
            conn.execute("PRAGMA foreign_keys=OFF")
            conn.executescript(f"""
                CREATE TABLE deals_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    deal_hash TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    store TEXT NOT NULL,
                    category TEXT NOT NULL
                        CHECK (category IN ({cats})),
                    price REAL,
                    original_price REAL,
                    discount_pct REAL,
                    unit_price REAL,
                    unit TEXT,
                    url TEXT NOT NULL,
                    image_url TEXT,
                    source TEXT NOT NULL DEFAULT 'slickdeals_rss',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    is_historical_low INTEGER NOT NULL DEFAULT 0,
                    coupon_available INTEGER NOT NULL DEFAULT 0,
                    first_seen TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_seen TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    scope TEXT NOT NULL DEFAULT 'unknown'
                );
                INSERT INTO deals_new SELECT * FROM deals;
                DROP TABLE deals;
                ALTER TABLE deals_new RENAME TO deals;
                CREATE INDEX idx_deals_category ON deals(category);
                CREATE INDEX idx_deals_store ON deals(store);
                CREATE INDEX idx_deals_active ON deals(is_active);
                CREATE INDEX idx_deals_last_seen ON deals(last_seen);
            """)
            conn.execute("PRAGMA foreign_keys=ON")
        # One-time backfill of fulfillment scope from title signals
        # (only touches never-classified rows, so it is idempotent).
        conn.execute(
            """UPDATE deals SET scope='local' WHERE scope='unknown' AND (
               lower(title) LIKE '%in-store%' OR lower(title) LIKE '%in store only%' OR
               lower(title) LIKE '%pickup%' OR lower(title) LIKE '%pick up%' OR
               lower(title) LIKE '%warehouse%' OR lower(title) LIKE '%in club only%')""")
        conn.execute(
            """UPDATE deals SET scope='online' WHERE scope='unknown' AND (
               lower(title) LIKE '%free shipping%' OR lower(title) LIKE '%free s&h%' OR
               lower(title) LIKE '%ships free%' OR lower(title) LIKE '%online only%')""")
        # Seed watchlist from config/watchlist.json. INSERT OR IGNORE makes
        # this idempotent, so new keywords added later merge in on next init.
        if config.WATCHLIST_PATH.exists():
            entries = json.loads(config.WATCHLIST_PATH.read_text(encoding="utf-8"))
            for e in entries:
                conn.execute(
                    """INSERT OR IGNORE INTO watchlist
                       (keyword, synonyms, category, min_discount_pct, enabled)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        e["keyword"],
                        __import__("json").dumps(e.get("synonyms", [])),
                        e.get("category"),
                        e.get("min_discount_pct", 20.0),
                        1 if e.get("enabled", True) else 0,
                    ),
                )
        conn.commit()
    return path

def get_setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default

def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """INSERT INTO settings (key, value, updated_at)
           VALUES (?, ?, CURRENT_TIMESTAMP)
           ON CONFLICT(key) DO UPDATE SET value=excluded.value,
           updated_at=CURRENT_TIMESTAMP""",
        (key, value),
    )
    conn.commit()
