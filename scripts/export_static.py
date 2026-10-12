"""Export a static snapshot for GitHub Pages: DB -> public/data.json.

Also sanitizes the database before it is committed back to the repo
(providers keys must never leak — CI injects them via Secrets instead).
Run: .venv/Scripts/python scripts/export_static.py
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from app import config, database  # noqa: E402
from app.main import (  # noqa: E402  (reuse display helpers; no server starts)
    _display_title, _source_label, _when_label, merchant_shop_url,
)

PUBLIC = BASE / "public"
LIMIT = 400


def main() -> None:
    database.init_db()
    with database.get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM deals WHERE is_active=1 "
            "ORDER BY last_seen DESC LIMIT ?", (LIMIT,)).fetchall()
        deals = []
        for r in rows:
            d = dict(r)
            d["display_title"] = _display_title(d.get("title", ""))
            d["store"] = _display_title(d.get("store", "")) or d.get("store", "")
            d["when_label"] = _when_label(d.get("last_seen"))
            d["source_label"] = _source_label(d.get("source"))
            d["hot"] = bool(d.get("is_historical_low")) or (d.get("discount_pct") or 0) >= 20
            d["shop_url"] = merchant_shop_url(d.get("store", ""), d["display_title"])
            deals.append(d)
        stats = {
            "total": conn.execute("SELECT COUNT(*) c FROM deals WHERE is_active=1").fetchone()["c"],
            "coupons": conn.execute("SELECT COUNT(*) c FROM coupons WHERE is_active=1").fetchone()["c"],
        }
        runs = [dict(r) for r in conn.execute(
            "SELECT source, MAX(finished_at) last_run FROM scrape_runs GROUP BY source").fetchall()]
        zip_code = database.get_setting(conn, "zip_code", config.ZIP_CODE) or config.ZIP_CODE
        # Sanitize before commit: provider keys live in Secrets, never in git.
        conn.execute("DELETE FROM settings WHERE key LIKE '%key' OR key LIKE '%base' OR key='zip_code'")
        # Retain 30 days of price history so the committed DB stays small.
        conn.execute("DELETE FROM price_history WHERE checked_at < datetime('now','-30 days')")
        conn.commit()
    with database.get_connection() as conn2:
        conn2.execute("VACUUM")
    PUBLIC.mkdir(exist_ok=True)
    (PUBLIC / "data.json").write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "zip_code": zip_code,
        "stats": stats,
        "runs": runs,
        "deals": deals,
    }, default=str), encoding="utf-8")
    print(f"exported {len(deals)} deals -> {PUBLIC / 'data.json'}")


if __name__ == "__main__":
    main()
