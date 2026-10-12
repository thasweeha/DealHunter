"""Extra deal-aggregator RSS feeds (§3.1) — verified live 2026-10-06.

- 9to5Toys: tech/electronics, ~50 items
- Hip2Save: groceries/household/personal-care + store coupons, ~200 items
- DealMania: tech roundups (fresh/empty feed as of check — auto-picks-up)
Skipped: KrazyCouponLady (no public RSS found).
No test modules — verify manually via POST /api/scan + dashboard.
"""
import logging
import time

import feedparser
import requests

from .slickdeals import UA, REQUEST_GAP_SECONDS, _parse_feed_content

log = logging.getLogger(__name__)

# (feed url, source label, default category, max items)
AGGREGATOR_FEEDS: list[tuple[str, str, str, int]] = [
    ("https://9to5toys.com/feed/", "9to5toys_rss", "electronics", 40),
    ("https://hip2save.com/feed/", "hip2save_rss", "groceries", 40),
    ("https://dealmania.me/feed/", "dealmania_rss", "electronics", 40),
    ("https://www.dansdeals.com/feed/", "dansdeals_rss", "groceries", 40),
    ("https://www.doctorofcredit.com/feed/", "doctorofcredit_rss", "groceries", 25),
    ("https://www.spoofee.com/rss.php", "spoofee_rss", "groceries", 40),
    ("https://www.spoofee.com/rsshot.php", "spoofee_hot_rss", "groceries", 15),
    ("https://feeds.feedburner.com/DealNews", "dealnews_rss", "electronics", 40),
]

def fetch_aggregators(
    feeds: list[tuple[str, str, str, int]] | None = None,
    timeout: int = 25,
) -> list:
    """Fetch aggregator feeds politely; skip dead/empty feeds, never raise."""
    from ..models import DealInput  # noqa: F401  (re-exported for callers)
    out: list = []
    for i, (url, source, default_cat, cap) in enumerate(feeds or AGGREGATOR_FEEDS):
        if i > 0:
            time.sleep(REQUEST_GAP_SECONDS)
        try:
            resp = requests.get(url, headers=UA, timeout=timeout)
            if resp.status_code == 429:
                log.warning("Rate-limited (429), stopping cycle at %s", url)
                break
            resp.raise_for_status()
            items = _parse_feed_content(resp.content, url, source, default_cat)[:cap]
            log.info("%s: %d deals", source, len(items))
            out.extend(items)
        except Exception as ex:  # noqa: BLE001
            log.warning("Aggregator fetch failed %s: %s", url, ex)
    return out
