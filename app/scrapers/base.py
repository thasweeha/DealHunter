"""Shared scraper plumbing: category guessing + scrape_run logging."""
import sqlite3
from datetime import datetime

CATEGORY_HINTS = {
    "electronics": ["laptop", "pc", "monitor", "display", "screen", "ssd", "gpu", "router",
                    "keyboard", "tv ", "oled", "qled", "cpu", "processor", "motherboard",
                    "mobo", " ram ", "ddr", " ryzen", " intel", "nvidia", "amd "],
    "groceries": ["coffee", "rice", "oil", "flour", "vegetable", "veggie", "produce"],
    "cleaning": ["detergent", "dish", "paper towel", "toilet paper", "trash bag", "clean"],
    "personal_care": ["hygiene", "shampoo", "soap", "toothpaste", "deodorant", "personal care"],
    "apparel": ["shirt", "t-shirt", "tee", "jeans", "denim", "jacket", "hoodie",
                "shoes", "sneaker", "boots", "sandals", "dress", "pants", "coat",
                "socks", "apparel", "clothing", "fashion", "blazer", "robe",
                "sweater", "polo", "suit", "skirt", "blouse", "shorts", "leggings",
                "pajamas", "underwear", "bra ", "handbag", "purse", "wallet",
                "belt", "scarf", "swim"],
    "home_tools": ["pillow", "bedding", "sheet", "blanket", "comforter", "cookware",
                   "wok", "frying pan", "saucepan", "knife set", "kitchen",
                   "tool", "drill", "saw ", "sander", "vacuum", "mop", "lamp",
                   "chair", "storage", "organizer", "luggage", "mattress",
                   "towel set", "curtain", "rug", "furniture"],
}

def guess_category(title: str) -> str:
    t = (title or "").lower()
    for cat, hints in CATEGORY_HINTS.items():
        if any(h in t for h in hints):
            return cat
    return "groceries"  # default bucket; matcher/watchlist refines

LOCAL_HINTS = ["in-store", "in store only", "pickup", "pick up", "warehouse",
               "in club only", "local store", "nearby"]
ONLINE_HINTS = ["free shipping", "free s&h", "ships free", "online only",
                "delivery", "+ free s&h"]

def classify_scope(title: str) -> str:
    """'local' (in-store/pickup near ZIP), 'online' (ships), else 'unknown'."""
    t = (title or "").lower()
    if any(h in t for h in LOCAL_HINTS):
        return "local"
    if any(h in t for h in ONLINE_HINTS):
        return "online"
    return "unknown"

def start_run(conn: sqlite3.Connection, source: str) -> int:
    cur = conn.execute("INSERT INTO scrape_runs (source, status) VALUES (?, 'running')", (source,))
    conn.commit()
    return cur.lastrowid

def finish_run(conn: sqlite3.Connection, run_id: int, found: int, matched: int, error: str | None = None):
    conn.execute(
        """UPDATE scrape_runs SET finished_at=CURRENT_TIMESTAMP, items_found=?,
           items_matched=?, status=?, error_msg=? WHERE id=?""",
        (found, matched, "error" if error else "success", error, run_id),
    )
    conn.commit()
