"""Coupon & promo-code signals (§3.1: RetailMeNot / Honey / store feeds).

RetailMeNot/Honey expose no public API, so this module harvests coupon
signals straight from deal text ("w/ code SAVE20", "clip coupon",
"digital coupon", "rebate", "BOGO/B1G1") and attaches them to deals —
that is what powers the COUPON badges + coupon-only filter.
TODO: direct RetailMeNot/store-feed lookup when a stable endpoint exists.
"""
import re

from ..models import CouponInput

_CODE_RE = re.compile(r"(?:use |with |w\/\s*)code\s+([A-Z0-9][A-Z0-9\-]{3,14})", re.IGNORECASE)
_CLIP_RE = re.compile(r"\b(clip|clippable|digital)\b.{0,12}\bcoupon\b|\bcoupon\b.{0,12}\b(clip|clippable|digital)\b", re.IGNORECASE)
_REBATE_RE = re.compile(r"\b(rebate|cash ?back)\b", re.IGNORECASE)
_BOGO_RE = re.compile(r"\b(BOGO|B1G1|buy one.{0,12}get one)\b", re.IGNORECASE)

def extract_coupon_signals(title: str, store: str) -> list[CouponInput]:
    """Detect coupon/rebate/BOGO signals in a deal title. Never raises."""
    out: list[CouponInput] = []
    t = title or ""
    m = _CODE_RE.search(t)
    if m:
        out.append(CouponInput(store=store, code=m.group(1).upper(),
                               description=f"Use code {m.group(1).upper()} at checkout",
                               source="deal_text"))
    elif re.search(r"\bw\/\s*code\b|\bwith code\b|\bpromo code\b|\bcoupon code\b", t, re.IGNORECASE):
        out.append(CouponInput(store=store, description="Promo/coupon code mentioned — see deal page",
                               source="deal_text"))
    if _CLIP_RE.search(t):
        out.append(CouponInput(store=store, description="Clippable/digital coupon on deal page",
                               source="deal_text"))
    if _REBATE_RE.search(t):
        out.append(CouponInput(store=store, description="Rebate/cashback available — see deal page",
                               source="deal_text"))
    if _BOGO_RE.search(t):
        out.append(CouponInput(store=store, description="BOGO offer — see deal page",
                               source="deal_text"))
    return out

def search_coupons(store: str, keyword: str) -> list[CouponInput]:
    # TODO: implement RetailMeNot / store coupon-feed lookup
    return []

def attach_coupons(conn, deal_hash: str, store: str, title: str) -> int:
    """Look up coupons for a deal, persist, flip coupon_available flag. Returns count."""
    found = search_coupons(store, title)
    for c in found:
        conn.execute(
            """INSERT OR IGNORE INTO coupons (store, code, description, promo_link, deal_hash, source)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (c.store, c.code, c.description, c.promo_link, deal_hash, c.source),
        )
    if found:
        conn.execute("UPDATE deals SET coupon_available = 1 WHERE deal_hash = ?", (deal_hash,))
    return len(found)
