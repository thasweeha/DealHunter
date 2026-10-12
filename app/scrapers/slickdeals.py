"""Deal RSS ingestion via feedparser (§3.1).

Live pipeline notes (verified manually 2026-10-06):
- Slickdeals `newsearch.php?...&format=rss` now returns bot-block HTML
  (JS-rendered results) instead of RSS -> skipped automatically; needs
  Playwright (see retailers.py TODO). Kept as opt-in via build_search_feeds().
- Reddit deal-aggregator RSS works with a browser UA but rate-limits
  aggressive polling (HTTP 429): default cycle uses 4 subs with a
  polite gap between requests and stops the cycle on first 429.
No test modules — verify manually via POST /api/scan + dashboard.
"""
import logging
import re
import time

import feedparser
import requests

from ..models import DealInput
from .base import guess_category

log = logging.getLogger(__name__)

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DealHunter/1.0"}
REQUEST_GAP_SECONDS = 4.0

# One sub per lane: electronics x3 + general/household x2 + warehouse x3.
# Keyword matching against the watchlist (not the sub) decides what gets
# stored/alerted. Dead subs (404) are skipped gracefully by fetch_rss.
DEFAULT_SUBS = ["LaptopDeals", "buildapcsales", "GameDeals", "coupons",
                "Frugal", "Costco", "SamsClub", "Target", "DollarTree",
                "FrugalMaleFashion", "SneakerDeals", "Newegg"]

def build_search_feeds(keywords: list[str] | None = None) -> list[str]:
    """Opt-in Slickdeals search feeds (currently bot-blocked, kept for Playwright/manual use)."""
    out = []
    for kw in keywords or ["laptop"]:
        q = requests.utils.quote(kw)
        out.append(
            f"https://slickdeals.net/newsearch.php?firstonly=1&q={q}"
            f"&pp=20&sort=newest&format=rss"
        )
    return out

def reddit_feeds(subs: list[str] | None = None) -> list[str]:
    return [f"https://www.reddit.com/r/{s}/new/.rss" for s in (subs or DEFAULT_SUBS)]

DEFAULT_FEEDS = reddit_feeds()

PRICE_RE = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})+(?:\.\d{2})?|\d+(?:\.\d{2})?)")
# Financing noise ("$118/mo", "$25 per month") must never become the price.
FINANCE_RE = re.compile(r"\$[\d,]+(?:\.\d{2})?\s*(?:/\s*mo\b|per month\b|\ba\s+month\b)", re.IGNORECASE)
STORE_RE = re.compile(r"@\s*([A-Za-z][\w&'.\- ]{1,30})")

_PREFIXED_STORES = [
    "Amazon", "Walmart", "Target", "Aldi", "Costco", "Best Buy", "Newegg",
    "eBay", "AliExpress", "KFC", "Home Depot", "Lowe's", "IKEA", "Dell",
    "Lenovo", "HP", "Apple", "Samsung", "DoorDash", "Instacart",
    "Dollar Tree", "Sam's Club", "Sams Club", "Newegg",
]
_STANDALONE_STORES = [
    "Amazon", "Walmart", "Target", "Aldi", "Costco", "Best Buy", "Newegg",
    "eBay", "AliExpress", "KFC", "Home Depot", "Lowe's", "IKEA",
    "Dollar Tree", "Sam's Club", "Sams Club", "Newegg",
]
_CANONICAL = {"Ebay": "eBay", "Aliexpress": "AliExpress", "Best buy": "Best Buy",
              "Home depot": "Home Depot", "Sams Club": "Sam's Club",
              "Dollar tree": "Dollar Tree"}

def _prefix_pattern(name: str) -> str:
    n = re.escape(name)
    return (r"[\[@\(\|]\s*" + n + r"\b"            # [Amazon] / (Costco / @Dell
            r"|\b(?:at|from|via|@)\s+" + n + r"\b"  # at Amazon / from Lenovo
            r"|\b" + n + r"\.com\b")                # Amazon.com

def extract_prices(*texts: str) -> tuple[float | None, float | None]:
    """From '$499 was $799' -> (499.0, 799.0). Single '$49' -> (49.0, None).

    Price = FIRST amount (deal titles lead with it); original = largest
    later amount above the price (ignores '$X/mo' financing noise).
    """
    found: list[float] = []
    for t in texts:
        if not t:
            continue
        t = FINANCE_RE.sub("", t)  # drop "$118/mo"-style financing noise first
        for m in PRICE_RE.findall(t):
            try:
                found.append(float(m.replace(",", "")))
            except ValueError:
                continue
    if not found:
        return None, None
    price = found[0]
    higher = [v for v in found[1:] if v > price]
    return price, (max(higher) if higher else None)

def extract_store(title: str, fallback: str = "Slickdeals") -> str:
    """Attribute the retailer from title cues: [Amazon], at Costco, @Dell...

    Ambiguous brands (Apple/Dell/...) only count with explicit prefix
    evidence (bracket, @, at/from/via, .com); unambiguous chains may also
    match standalone.
    """
    t = title or ""
    for name in _PREFIXED_STORES:
        if re.search(_prefix_pattern(name), t, re.IGNORECASE):
            return _CANONICAL.get(name, name)
    for name in _STANDALONE_STORES:
        if re.search(r"\b" + re.escape(name) + r"\b", t, re.IGNORECASE):
            return _CANONICAL.get(name, name)
    m = STORE_RE.search(t)
    if m:
        return m.group(1).strip().rstrip(".,)")
    return fallback

def _parse_feed_content(content: bytes, feed_url: str, source: str,
                        default_category: str | None = None) -> list[DealInput]:
    # Slickdeals bot-wall returns HTML here: skip quietly (needs Playwright).
    head = content[:500].lower()
    if b"<html" in head or b"<!doctype html" in head:
        log.info("Skipping non-RSS HTML response: %s", feed_url)
        return []
    parsed = feedparser.parse(content)
    if getattr(parsed, "bozo", False) and not parsed.entries:
        log.warning("RSS parse failed for %s: %s", feed_url, getattr(parsed, "bozo_exception", ""))
        return []
    sub = feed_url.split("/r/")[1].split("/")[0] if "/r/" in feed_url else ""
    fallback_store = f"Reddit r/{sub}" if sub else "Slickdeals"
    out: list[DealInput] = []
    for e in parsed.entries:
        title = getattr(e, "title", "Untitled deal") or "Untitled deal"
        link = getattr(e, "link", feed_url) or feed_url
        summary = getattr(e, "summary", "") or getattr(e, "description", "") or ""
        price, original = extract_prices(title, summary)
        image = None
        for attr in ("media_content", "media_thumbnail"):
            media = getattr(e, attr, None)
            if media and isinstance(media, list) and media[0].get("url"):
                image = media[0]["url"]
                break
        if not image:
            for link_obj in getattr(e, "links", []):
                if link_obj.get("rel") == "enclosure":
                    image = link_obj.get("href")
                    break
        out.append(DealInput(
            title=title, store=extract_store(title, fallback_store),
            category=_categorize(title, default_category),
            url=link, price=price, original_price=original,
            image_url=image, source=source,
        ))
    return out

def _categorize(title: str, default_category: str | None) -> str:
    """Per-title guess, unless the feed is single-lane (e.g. 9to5toys→tech)
    and the title carries no other lane's hints (guess falls back to the
    generic 'groceries' bucket)."""
    g = guess_category(title)
    if default_category and default_category != "groceries" and g == "groceries":
        return default_category
    return g

def _source_for(url: str) -> str:
    return "reddit_rss" if "reddit.com" in url else "slickdeals_rss"

def fetch_rss(feeds: list[str] | None = None, timeout: int = 20) -> list[DealInput]:
    """Fetch each RSS URL politely; skip dead feeds, never raise.

    Stops the cycle on HTTP 429 (rate-limit) so the next scheduled run
    retries instead of hammering.
    """
    out: list[DealInput] = []
    targets = feeds or DEFAULT_FEEDS
    for i, url in enumerate(targets):
        if i > 0:
            time.sleep(REQUEST_GAP_SECONDS)
        try:
            resp = requests.get(url, headers=UA, timeout=timeout)
            if resp.status_code == 429:
                log.warning("Rate-limited (429), stopping cycle at %s", url)
                break
            resp.raise_for_status()
            out.extend(_parse_feed_content(resp.content, url, _source_for(url)))
        except Exception as ex:  # noqa: BLE001 — one bad feed must not kill the run
            log.warning("RSS fetch failed %s: %s", url, ex)
    return out
