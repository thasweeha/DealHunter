"""FastAPI entry: dashboard + REST API (§3.4, §4). Run: uvicorn app.main:app --reload"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
from . import config, database
from .api.routes import router

BASE = Path(__file__).resolve().parent.parent

import logging as _logging
_log = _logging.getLogger("dealhunter")

# Module-level handle so /api/stats can report scheduler health.
scheduler_instance = None

def scheduler_status() -> dict:
    sched = scheduler_instance
    if sched is None:
        return {"active": False, "next_run": None}
    try:
        jobs = sched.get_jobs()
    except Exception:
        return {"active": False, "next_run": None}
    nxt = None
    if jobs and getattr(jobs[0], "next_run_time", None):
        nxt = jobs[0].next_run_time.isoformat()
    return {"active": True, "next_run": nxt}

@asynccontextmanager
async def lifespan(app: FastAPI):
    global scheduler_instance
    database.init_db()
    scheduler_instance = None
    try:
        from .scheduler import start_scheduler
        scheduler_instance = start_scheduler()
        _log.info("DealHunter scheduler started: %s", scheduler_status())
    except Exception as ex:  # noqa: BLE001 — loud, never silent
        _log.exception("DealHunter scheduler FAILED to start: %s", ex)
    yield
    if scheduler_instance is not None:
        scheduler_instance.shutdown(wait=False)
        scheduler_instance = None

import re
import urllib.parse
from datetime import datetime

_FOUND_BY_RE = re.compile(r"\s*(Found by|Last Comment by) .*$", re.DOTALL)

def _display_title(raw: str) -> str:
    """Strip scraper tails like 'Found by X · Today 10:54 AM $...' for card titles."""
    t = _FOUND_BY_RE.sub("", raw or "").strip()
    return re.sub(r"\s+", " ", t)

def _when_label(seen: str | None) -> str:
    """'Today 2:00 AM' for same-day, else 'Oct 4, 2026 2:01 AM'."""
    if not seen:
        return ""
    try:
        dt = datetime.strptime(seen.split(".")[0], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return seen
    hm = dt.strftime("%I:%M %p").lstrip("0")
    if dt.date() == datetime.now().date():
        return f"Today {hm}"
    return f"{dt.strftime('%b')} {dt.day}, {dt.year} {hm}"

def _source_label(source: str | None) -> str:
    s = (source or "").lower()
    if "slickdeals" in s:
        return "Slickdeals"
    if "reddit" in s:
        return "Reddit"
    if "walmart" in s:
        return "Walmart"
    if "target" in s:
        return "Target"
    if "aldi" in s:
        return "Aldi"
    return (source or "Deal").replace("_pw", "").replace("_", " ").title()

# Direct merchant search links so a card never dead-ends at an aggregator
# thread (e.g. Costco.com hides warehouse-only items behind member login —
# the 🔍 link searches the merchant site for the same product).
SHOP_SEARCH = {
    "costco": "https://www.costco.com/s?keyword={q}",
    "samsclub": "https://www.samsclub.com/s/{q}",
    "bestbuy": "https://www.bestbuy.com/site/searchpage.jsp?st={q}",
    "walmart": "https://www.walmart.com/search?q={q}",
    "target": "https://www.target.com/s?searchTerm={q}",
    "dollartree": "https://www.dollartree.com/search/go?w={q}",
    "amazon": "https://www.amazon.com/s?k={q}",
    "newegg": "https://www.newegg.com/p/pl?d={q}",
    "dell": "https://www.dell.com/en-us/shop/search/{q}",
    "lenovo": "https://www.lenovo.com/us/en/search?text={q}",
}
_SHOP_STOPWORDS = {
    "free", "shipping", "deal", "deals", "sale", "hot", "new", "only", "with",
    "code", "coupon", "coupons", "get", "buy", "save", "off", "was", "for",
    "and", "the", "from", "plus", "ship", "ships", "shipped", "card",
    "limited", "time", "offer", "today", "now", "store", "online", "ymmv",
}

def _shop_key(store: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (store or "").lower())

def merchant_shop_url(store: str, title: str) -> str | None:
    """Merchant-site search URL for this deal's product keywords (or None)."""
    tpl = SHOP_SEARCH.get(_shop_key(store))
    if not tpl:
        return None
    words = re.findall(r"[A-Za-z0-9']+", title or "")
    keep = [w for w in words
            if len(w) > 2 and w.lower() not in _SHOP_STOPWORDS
            and not w.replace(",", "").replace(".", "").isdigit()]
    if not keep:
        return None
    return tpl.format(q=urllib.parse.quote_plus(" ".join(keep[:6])))

app = FastAPI(title="DealHunter", lifespan=lifespan)
app.include_router(router)
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE / "templates"))

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    with database.get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM deals WHERE is_active=1 ORDER BY last_seen DESC LIMIT 400").fetchall()
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
        stats["local"] = sum(1 for d in deals if d.get("scope") == "local")
    local_deals = [d for d in deals if d.get("scope") == "local"]
    wide_deals = [d for d in deals if d.get("scope") != "local"]
    return templates.TemplateResponse(request, "dashboard.html",
        {"deals": deals, "local_deals": local_deals, "wide_deals": wide_deals,
         "stats": stats, "runs": runs, "zip_code": zip_code})
