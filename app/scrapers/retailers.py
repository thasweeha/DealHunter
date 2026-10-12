"""Retailer monitoring: Slickdeals (Playwright, JS-rendered) + Walmart/Target/Aldi.

Slickdeals search results are JS-rendered (static fetch gets a bot-wall
shell), so this module renders pages headless and parses deal cards with
BeautifulSoup. Walmart/Target/Aldi are best-effort: all three run strong
bot mitigation that usually blocks headless browsers — failures are
logged and yield [] so the pipeline never breaks.
No test modules — verify manually via POST /api/scan + dashboard.
"""
import logging
import time
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup

from ..models import DealInput
from .. import config
from .base import guess_category
from .slickdeals import extract_prices, extract_store

log = logging.getLogger(__name__)

REAL_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
PAGE_TIMEOUT_MS = 45000
# Keep the 30-min cycle snappy: cap page loads per scan.
SD_KEYWORDS = ["laptop", "paper towels", "coffee", "costco",
               "laundry detergent", "shampoo", "best buy", "dollar tree",
               "shoes", "newegg", "clearance", "target", "walmart",
               "home depot", "lowes"]

# Merchant-scoped SD searches imply this store when the title is silent.
_MERCHANT_KEYWORDS = {
    "newegg": "Newegg", "best buy": "Best Buy", "costco": "Costco",
    "dollar tree": "Dollar Tree", "sams club": "Sam's Club",
    "target": "Target", "walmart": "Walmart",
    "home depot": "Home Depot", "lowes": "Lowe's",
}
RETAILER_KEYWORDS = ["paper towels", "laundry detergent"]


def _render(url: str, wait_css: str | None = None) -> str:
    """Render a JS-heavy page headless and return final HTML ('' on failure)."""
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=[
                "--disable-blink-features=AutomationControlled",
            ])
            page = browser.new_page(user_agent=REAL_UA, locale="en-US")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
                if wait_css:
                    try:
                        page.wait_for_selector(wait_css, timeout=15000)
                    except Exception:
                        pass  # parse whatever rendered anyway
                page.wait_for_timeout(2500)
                return page.content()
            finally:
                browser.close()
    except Exception as ex:  # noqa: BLE001
        log.warning("Playwright render failed %s: %s", url, ex)
        return ""


def _cards_to_deals(html: str, page_url: str, store: str, source: str,
                    max_items: int = 10) -> list[DealInput]:
    """Generic card parser: anchors with deal-like hrefs + $-prices in text."""
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    deals: list[DealInput] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href: str = a["href"]
        if not any(k in href for k in ("/f/", "/d/", "/product", "/p/", "/weekly", "/deal")):
            continue
        url = urljoin(page_url, href.split("?")[0].split("#")[0])
        if url in seen or len(url) > 300:
            continue
        # Card scope: nearest li/article/div with an image + text.
        card = a.find_parent(["li", "article", "div"])
        text = (card.get_text(" ", strip=True) if card else a.get_text(" ", strip=True)) or ""
        if len(text) < 25 or len(text) > 600:
            continue
        price, original = extract_prices(text)
        if price is None:
            continue  # price-less nav links are noise
        img = None
        if card:
            tag = card.find("img", src=True)
            if tag:
                img = urljoin(page_url, tag.get("data-src") or tag["src"])
        title = text[:180]
        deals.append(DealInput(
            title=title, store=extract_store(title, store),
            category=guess_category(title), url=url,
            price=price, original_price=original, image_url=img, source=source,
        ))
        seen.add(url)
        if len(deals) >= max_items:
            break
    return deals


def _price_led_deals(html: str, base: str, store: str, source: str,
                     link_hints: tuple[str, ...], max_items: int = 25) -> list[DealInput]:
    """Price-led parser for retailer hubs (Dell/Lenovo-style) where prices sit
    in card containers rather than anchor text: walk up from each $ amount to
    the nearest container holding a product link."""
    import re as _re
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    deals: list[DealInput] = []
    seen: set[str] = set()
    price_pat = _re.compile(r"^\$[\d,]+(?:\.\d{2})?$")
    for s in soup.find_all(string=price_pat):
        txt = (s or "").strip()
        if not txt or len(txt) > 15:
            continue
        box = s.parent
        links: list = []
        for _ in range(6):
            box = box.parent if box is not None else None
            if box is None or getattr(box, "name", None) in ("body", "html", "[document]"):
                break
            if len(box.get_text(" ", strip=True)) > 2500:
                continue
            links = [a for a in box.find_all("a", href=True)
                     if any(h in a["href"] for h in link_hints)]
            if links:
                break
        if not links:
            continue
        url = urljoin(base, links[0]["href"].split("?")[0].split("#")[0])
        if url in seen or len(url) > 300:
            continue
        title, img = "", None
        for htag in ("h2", "h3", "h4", "h5"):
            for h in box.find_all(htag):
                t = h.get_text(" ", strip=True)
                if len(t) > len(title):
                    title = t
        for tag in box.find_all("img", src=True):
            src = tag.get("src", "")
            if src.startswith("data:") or "logo" in src.lower() or "icon" in src.lower():
                continue
            if img is None:
                img = urljoin(base, tag.get("data-src") or src)
            alt = (tag.get("alt") or "").strip()
            if len(alt) > len(title) and len(alt) > 10:
                title = alt
            if img is not None and len(title) > 15:
                break
        if len(title) < 15:
            banned = ("out of 5 stars", "reviews", "rating", "compare",
                      "view more", "save ", "shop now", "learn more")
            for a in links:
                t = a.get_text(" ", strip=True)
                low = t.lower()
                if any(b in low for b in banned):
                    continue
                if len(t) > len(title):
                    title = t
        if len(title) < 15 or any(b in title.lower() for b in
                                  ("est value", "estimated value", "view more details",
                                   "out of 5 stars", "add to cart", "quick view")):
            # Name lives in a sibling subtree (e.g. Lenovo image column):
            # peek one level up at headings, image alts, and product anchors.
            up = box.parent if box is not None else None
            if up is not None and getattr(up, "name", None) not in ("body", "html", "[document]"):
                for htag in ("h2", "h3", "h4", "h5"):
                    for h in up.find_all(htag):
                        t = h.get_text(" ", strip=True)
                        if len(t) > len(title):
                            title = t
                for tag in up.find_all("img", src=True):
                    alt = (tag.get("alt") or "").strip()
                    if len(alt) > len(title) and len(alt) > 10 \
                            and "logo" not in (tag.get("src", "").lower()):
                        title = alt
                for a in up.find_all("a", href=True):
                    if not any(h in a["href"] for h in link_hints):
                        continue
                    t = a.get_text(" ", strip=True)
                    low = t.lower()
                    if len(t) < 15 or any(b in low for b in
                                          ("view more", "learn more", "quick view",
                                           "add to cart", "out of 5 stars")):
                        continue
                    if len(t) > len(title):
                        title = t
        text = box.get_text(" ", strip=True)
        price, original = extract_prices(text)
        if price is None:
            continue
        title = (title or text[:80])[:180]
        deals.append(DealInput(
            title=title, store=extract_store(title, store),
            category=guess_category(title), url=url,
            price=price, original_price=original, image_url=img, source=source,
        ))
        seen.add(url)
        if len(deals) >= max_items:
            break
    return deals


def fetch_slickdeals_playwright(keywords: list[str] | None = None) -> list[DealInput]:
    """Render Slickdeals search pages and extract deal cards incl. thumbnails."""
    out: list[DealInput] = []
    for kw in keywords or SD_KEYWORDS:
        url = (f"https://slickdeals.net/newsearch.php?firstonly=1&q={quote_plus(kw)}"
               f"&pp=20&sort=newest")
        html = _render(url)
        found = _cards_to_deals(html, url, "Slickdeals", "slickdeals_pw")
        # Merchant-scoped searches (e.g. "newegg") imply the merchant when
        # the title itself names no other store.
        merchant = _MERCHANT_KEYWORDS.get(kw.strip().lower())
        if merchant:
            for d in found:
                if d.store == "Slickdeals":
                    d.store = merchant
        log.info("Slickdeals[%s]: %d deals", kw, len(found))
        out.extend(found)
        time.sleep(2)
    return out


def _retailer_search(store: str, base: str, url_tpl: str,
                    keywords: list[str] | None = None) -> list[DealInput]:
    out: list[DealInput] = []
    for kw in keywords or RETAILER_KEYWORDS:
        page_url = url_tpl.format(q=quote_plus(kw))
        html = _render(page_url)
        found = _cards_to_deals(html, base, store, f"{store.lower()}_pw")
        # Direct retailer listings are inherently local (store context + ZIP).
        for d in found:
            d.scope = "local"
        log.info("%s[%s]: %d deals", store, kw, len(found))
        out.extend(found)
        time.sleep(2)
    return out


def fetch_walmart(zip_code: str | None = None) -> list[DealInput]:
    return _retailer_search("Walmart", "https://www.walmart.com",
        "https://www.walmart.com/search?q={q}&sort=price_low")

def fetch_target(zip_code: str | None = None) -> list[DealInput]:
    return _retailer_search("Target", "https://www.target.com",
        "https://www.target.com/s?searchTerm={q}&sortBy=PriceLow")

ALDI_PAGES = [
    "https://www.aldi.us/store/aldi/pages/aldi-finds",
    "https://www.aldi.us/weekly-ads/",
]

def fetch_aldi(zip_code: str | None = None) -> list[DealInput]:
    """ALDI Finds + weekly ad (JS-rendered; static fetch returns an empty shell)."""
    out: list[DealInput] = []
    for url in ALDI_PAGES:
        html = _render(url)
        found = _cards_to_deals(html, "https://www.aldi.us/", "Aldi", "aldi_pw")
        log.info("Aldi[%s]: %d deals", url.split("/store/")[-1][:40], len(found))
        out.extend(found)
        time.sleep(2)
    for d in out:
        d.scope = "local"  # weekly in-store assortment near ZIP
    return out

CONTENTEGG_PAGES = [
    "https://dealmania.me/prime-big-day-deals/",
]

def _parse_contentegg(html: str, page_url: str, base: str, store: str,
                      source: str, max_items: int = 25) -> list[DealInput]:
    """Parse ContentEgg deal rows (cegg-price / cegg-old-price / cegg-card).

    Used by DealMania and similar WordPress deal portals where the price,
    product link and buy button are sibling cells rather than nested anchors.
    """
    from urllib.parse import urlparse
    soup = BeautifulSoup(html, "html.parser")
    deals: list[DealInput] = []
    seen: set[str] = set()
    for price_el in soup.select(".cegg-price"):
        row = price_el.find_parent("div", class_="row") or price_el.parent
        old_el = row.select_one(".cegg-old-price") if row else None
        price, original = extract_prices(
            price_el.get_text(" ", strip=True),
            old_el.get_text(" ", strip=True) if old_el else "",
        )
        if price is None:
            continue
        # Product link: first outbound anchor (often an empty buy button).
        # Title: longest anchor text, else the product image alt text.
        url, title = "", ""
        if row:
            for a in row.find_all("a", href=True):
                href = a["href"]
                if not href.startswith("http") or len(href) > 300:
                    continue
                if not url:
                    url = href
                t = a.get_text(" ", strip=True)
                if len(t) > len(title):
                    title = t
        if not url or url in seen:
            continue
        url = urljoin(base, url)
        # Merchant: store-logo alt text beats title guessing.
        merchant = ""
        if row:
            logo = row.select_one(".cegg-store-logos-col img")
            if logo and logo.get("alt"):
                merchant = logo["alt"].strip()
        img = None
        if row:
            for tag in row.find_all("img", src=True):
                src = tag["src"]
                if "DM.png" in src or src.startswith("data:"):
                    continue
                if "content-egg/res/logos" in src:
                    continue  # merchant logo, not the product
                img = urljoin(base, src)
                if not title and tag.get("alt"):
                    title = tag["alt"].strip()
                break
        title = (title or "DealMania deal")[:180]
        host_store = urlparse(url).netloc.replace("www.", "").split(".")[0].title()
        deals.append(DealInput(
            title=title,
            store=extract_store(f"{title} at {merchant}" if merchant else title,
                                merchant or host_store or store),
            category=guess_category(title), url=url,
            price=price, original_price=original, image_url=img, source=source,
            scope="online",  # roundup links ship (Amazon dp links)
        ))
        seen.add(url)
        if len(deals) >= max_items:
            break
    return deals

def fetch_dealmania(pages: list[str] | None = None) -> list[DealInput]:
    """DealMania roundup pages (static WordPress/ContentEgg, BS4-friendly).

    Add more ContentEgg-based portals to CONTENTEGG_PAGES as discovered.
    """
    out: list[DealInput] = []
    for url in pages or CONTENTEGG_PAGES:
        try:
            import requests as _rq
            from .slickdeals import UA as _UA
            resp = _rq.get(url, headers=_UA, timeout=25)
            resp.raise_for_status()
            found = _parse_contentegg(resp.text, url, "https://dealmania.me/",
                                      "DealMania", "dealmania_pw")
            log.info("DealMania: %d deals", len(found))
            out.extend(found)
        except Exception as ex:  # noqa: BLE001
            log.warning("DealMania fetch failed %s: %s", url, ex)
    return out

def fetch_all_retailers(zip_code: str | None = None) -> list[DealInput]:
    zip_code = zip_code or config.ZIP_CODE
    deals: list[DealInput] = []
    for fn in (fetch_slickdeals_playwright, fetch_dealmania, fetch_dell,
               fetch_lenovo, fetch_newegg_hub,
               fetch_walmart, fetch_target, fetch_aldi):
        try:
            if fn in (fetch_slickdeals_playwright, fetch_dealmania, fetch_dell,
                      fetch_lenovo, fetch_newegg_hub):
                deals.extend(fn())
            else:
                deals.extend(fn(zip_code))
        except Exception as ex:  # noqa: BLE001
            log.warning("Retailer fetch %s failed: %s", getattr(fn, "__name__", fn), ex)
    return deals


def fetch_dell() -> list[DealInput]:
    """Dell deals hub (JS-rendered; static fetch is 403-walled)."""
    html = _render("https://www.dell.com/en-us/shop/deals")
    found = _price_led_deals(html, "https://www.dell.com/", "Dell", "dell_pw", ("/spd/",))
    for d in found:
        d.scope = "online"
    log.info("Dell: %d deals", len(found))
    return found


def fetch_lenovo() -> list[DealInput]:
    """Lenovo deals hub (JS-rendered product pods)."""
    html = _render("https://www.lenovo.com/us/en/d/deals/")
    found = _price_led_deals(html, "https://www.lenovo.com/", "Lenovo", "lenovo_pw", ("/p/",))
    for d in found:
        d.scope = "online"
    log.info("Lenovo: %d deals", len(found))
    return found


def fetch_newegg_hub() -> list[DealInput]:
    """Newegg Shell Shocker hub (static HTML — no browser needed)."""
    out: list[DealInput] = []
    try:
        import requests as _rq
        from .slickdeals import UA as _UA
        resp = _rq.get("https://www.newegg.com/todays-deals", headers=_UA, timeout=25)
        resp.raise_for_status()
        out = _cards_to_deals(resp.text, "https://www.newegg.com/", "Newegg", "newegg_pw",
                              max_items=25)
        log.info("Newegg hub: %d deals", len(out))
    except Exception as ex:  # noqa: BLE001
        log.warning("Newegg hub fetch failed: %s", ex)
    for d in out:
        d.scope = "online"
    return out
