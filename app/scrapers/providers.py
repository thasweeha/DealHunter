"""Key-gated providers: Takeads, SerpApi Google Shopping, Strackr.

All fetchers skip gracefully when unconfigured so the pipeline never
breaks. Keys resolve DB settings (dashboard) first, env (.env) second.

- Takeads (Mitgo): documented REST — coupon list + per-URL coupon search.
  Free publisher account at takeads.com. No test modules — verify manually.
- SerpApi Google Shopping: zip-localized live prices. Free tier ~100
  searches/mo, so this module self-throttles to one run per 24h.
- Strackr: account-specific REST/CSV export — needs key + the export URL
  from your Strackr dashboard (see .env.example).
"""
import csv
import io
import logging
import os
import time
from datetime import datetime, timedelta

import requests

log = logging.getLogger(__name__)

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DealHunter/1.0"}


def _key(conn, setting: str, env_var: str) -> str:
    from .. import database
    try:
        v = database.get_setting(conn, setting, "") or ""
    except Exception:
        v = ""
    return (v or os.getenv(env_var, "") or "").strip()


# ---------------------------------------------------------------- Takeads
TAKEADS_COUPONS_URL = "https://api.takeads.com/v1/product/monetize-api/v1/coupon"
TAKEADS_SEARCH_URL = TAKEADS_COUPONS_URL + "/search"


def _takeads_key(conn) -> str:
    return _key(conn, "takeads_key", "TAKEADS_KEY")


def fetch_takeads_coupons(conn, limit: int = 100) -> list | None:
    """General active coupon feed (US). None when unconfigured (skip run)."""
    from ..models import CouponInput
    key = _takeads_key(conn)
    if not key:
        return None
    resp = requests.get(
        TAKEADS_COUPONS_URL,
        headers={"Authorization": f"Bearer {key}"},
        params={"isActive": "true", "limit": limit, "countryCodes": "US"},
        timeout=30,
    )
    resp.raise_for_status()
    out = []
    for c in resp.json().get("data", []):
        if not c.get("isActive", True):
            continue
        out.append(CouponInput(
            store="Takeads",
            code=c.get("code"),
            description=c.get("name") or c.get("description"),
            promo_link=c.get("trackingLink"),
            source="takeads",
        ))
    return out


def match_takeads_for_urls(conn, urls: list[str]) -> dict:
    """Real promo codes for OUR deal URLs via Takeads coupon search.

    Returns {url: [CouponInput(code, promo_link, ...)]} — caller stamps the
    deal's own store on attach so retailer filtering stays clean.
    """
    from ..models import CouponInput
    key = _takeads_key(conn)
    urls = [u for u in urls if u and u.startswith("http")][:20]
    if not key or not urls:
        return {}
    resp = requests.post(
        TAKEADS_SEARCH_URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"iris": urls},
        timeout=30,
    )
    resp.raise_for_status()
    out: dict = {}
    for item in resp.json().get("data", []):
        found = []
        for c in item.get("coupons", []):
            found.append(CouponInput(
                store="",  # stamped by caller with the deal's store
                code=c.get("code"),
                description=c.get("name") or c.get("description"),
                promo_link=c.get("trackingLink"),
                source="takeads",
            ))
        if found:
            out[item.get("iri", "")] = found
    return out


# ---------------------------------------------------------------- SerpApi
SERPAPI_QUERIES = ["laptop", "paper towels", "coffee"]
SERPAPI_MIN_HOURS_BETWEEN_RUNS = 24  # free tier is ~100 searches/month


def serpapi_due(conn) -> bool:
    row = conn.execute(
        "SELECT MAX(finished_at) AS m FROM scrape_runs "
        "WHERE source='serpapi' AND finished_at IS NOT NULL"
    ).fetchone()
    if not row or not row["m"]:
        return True
    try:
        last = datetime.strptime(row["m"].split(".")[0], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return True
    return datetime.now() - last >= timedelta(hours=SERPAPI_MIN_HOURS_BETWEEN_RUNS)


def fetch_serpapi(conn) -> list | None:
    """Zip-localized Google Shopping prices. None when unconfigured or
    throttled (free tier: 1 run / 24h) so no empty run is recorded."""
    from ..models import DealInput
    from .base import guess_category
    from .slickdeals import extract_prices, extract_store
    key = _key(conn, "serpapi_key", "SERPAPI_KEY")
    if not key:
        return None
    if not serpapi_due(conn):
        log.info("SerpApi: throttled (free tier) — next run after 24h window")
        return None
    from .. import database
    from .. import config
    zip_code = database.get_setting(conn, "zip_code", config.ZIP_CODE) or config.ZIP_CODE
    out = []
    for i, q in enumerate(SERPAPI_QUERIES):
        if i:
            time.sleep(2)
        resp = requests.get(
            "https://serpapi.com/search.json",
            params={"engine": "google_shopping", "q": q, "location": zip_code,
                    "google_domain": "google.com", "gl": "us", "num": "20",
                    "api_key": key},
            headers=UA, timeout=30,
        )
        resp.raise_for_status()
        for r in resp.json().get("shopping_results", []):
            title = r.get("title", "") or "Untitled deal"
            price = r.get("extracted_price")
            if price is None:
                price, _ = extract_prices(title)
            merchant = r.get("source", "") or "Google Shopping"
            out.append(DealInput(
                title=title, store=extract_store(title, merchant),
                category=guess_category(title),
                url=r.get("link", "") or "https://www.google.com/shopping",
                price=price, original_price=r.get("extracted_old_price"),
                image_url=r.get("thumbnail"), source="serpapi",
            ))
    return out


# ---------------------------------------------------------------- Strackr
def fetch_strackr(conn) -> list | None:
    """Strackr deals export. None when unconfigured (skip run).
    Strackr issues account-specific REST/CSV endpoints (see their dashboard
    and .env.example). Accepts JSON lists or CSV; maps common columns."""
    from ..models import CouponInput
    key = _key(conn, "strackr_key", "STRACKR_KEY")
    base = _key(conn, "strackr_base", "STRACKR_API_BASE")
    if not key or not base:
        return None
    resp = requests.get(base, headers={"Authorization": f"Bearer {key}", **UA}, timeout=30)
    resp.raise_for_status()
    out = []
    ctype = resp.headers.get("Content-Type", "")
    rows: list[dict] = []
    if "csv" in ctype or base.lower().endswith(".csv"):
        rows = list(csv.DictReader(io.StringIO(resp.text)))
    else:
        data = resp.json()
        rows = data if isinstance(data, list) else data.get("data", data.get("deals", []))
    for r in rows:
        if not isinstance(r, dict):
            continue
        title = r.get("title") or r.get("name") or ""
        if not title:
            continue
        out.append(CouponInput(
            store=r.get("merchant") or r.get("store") or r.get("advertiser") or "Strackr",
            code=r.get("code") or r.get("promo_code"),
            description=r.get("description") or title,
            promo_link=r.get("url") or r.get("link") or r.get("tracking_link"),
            source="strackr",
        ))
    return out
