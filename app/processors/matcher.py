"""Watchlist matching against keywords + synonyms. Returns matched entry or None."""
import json
import sqlite3

def load_watchlist(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT keyword, synonyms, category, min_discount_pct FROM watchlist WHERE enabled = 1"
    ).fetchall()
    out = []
    for r in rows:
        try:
            syns = json.loads(r["synonyms"] or "[]")
        except Exception:
            syns = []
        out.append({
            "keyword": r["keyword"],
            "synonyms": syns,
            "category": r["category"],
            "min_discount_pct": r["min_discount_pct"],
        })
    return out

def match_deal(title: str, category: str | None, discount_pct: float | None,
               watchlist: list[dict], store: str | None = None) -> dict | None:
    """Keyword/synonym match on the title; a watchlist keyword may also match
    the attributed store (e.g. keyword 'aldi' catches curated retailer-direct
    finds whose titles don't name the store). Category-scoped entries still
    require a category match; priced items must clear the entry threshold."""
    text = (title or "").lower()
    store_text = (store or "").lower()
    for entry in watchlist:
        terms = [entry["keyword"].lower(), *[s.lower() for s in entry["synonyms"]]]
        if entry.get("category") and category and entry["category"] != category:
            continue  # category-scoped entry
        hit = any(t and t in text for t in terms)
        if not hit and store_text:
            hit = any(t and t == store_text for t in terms)
        if hit:
            threshold = entry.get("min_discount_pct", 20.0)
            if discount_pct is None or discount_pct >= threshold:
                return entry
    return None
