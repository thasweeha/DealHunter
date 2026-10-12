"""Dedup + upsert helpers: deal_hash = sha256(title|url).

Store is deliberately excluded: retailer attribution improves over time
(e.g. 'Reddit r/x' -> 'Amazon') and must update rows in place, not fork
duplicates.
"""
import hashlib

def make_deal_hash(title: str, store: str, url: str) -> str:
    base = f"{(title or '').strip().lower()}|{(url or '').strip()}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:32]

def is_known(conn, deal_hash: str) -> bool:
    """True if this deal was stored by an earlier scan (price tracking)."""
    return conn.execute(
        "SELECT 1 FROM deals WHERE deal_hash = ?", (deal_hash,)
    ).fetchone() is not None

def upsert_deal(conn, deal_hash: str, title: str, store: str, category: str,
               price, original_price, discount_pct, unit_price, unit,
               url: str, image_url, source: str, expires_at=None,
               scope: str = "unknown") -> bool:
    """Insert or refresh deal + append price_history. Returns True if newly inserted."""
    cur = conn.execute("SELECT price FROM deals WHERE deal_hash = ?", (deal_hash,))
    row = cur.fetchone()
    if row is None:
        conn.execute(
            """INSERT INTO deals (deal_hash, title, store, category, price, original_price,
                                  discount_pct, unit_price, unit, url, image_url, source, expires_at, scope)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (deal_hash, title, store, category, price, original_price, discount_pct,
             unit_price, unit, url, image_url, source, expires_at, scope),
        )
        is_new = True
    else:
        conn.execute(
            """UPDATE deals SET title=?, store=?, category=?, price=?, original_price=?,
               discount_pct=?, unit_price=?, unit=?, url=?, image_url=?, source=?,
               scope=?, last_seen=CURRENT_TIMESTAMP, is_active=1 WHERE deal_hash=?""",
            (title, store, category, price, original_price, discount_pct,
             unit_price, unit, url, image_url, source, scope, deal_hash),
        )
        is_new = False
    if price is not None:
        conn.execute(
            "INSERT INTO price_history (deal_hash, price, original_price) VALUES (?, ?, ?)",
            (deal_hash, price, original_price),
        )
        # historical-low flag: true if this price is the min seen
        low = conn.execute(
            "SELECT MIN(price) FROM price_history WHERE deal_hash = ?", (deal_hash,)
        ).fetchone()[0]
        conn.execute(
            "UPDATE deals SET is_historical_low = ? WHERE deal_hash = ?",
            (1 if low is not None and price <= low else 0, deal_hash),
        )
    return is_new

def already_alerted(conn, deal_hash: str, channel: str = "telegram") -> bool:
    return conn.execute(
        "SELECT 1 FROM alerts WHERE deal_hash = ? AND channel = ?", (deal_hash, channel)
    ).fetchone() is not None
