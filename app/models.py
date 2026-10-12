"""Typed record shapes shared by scrapers / processors / API."""
from dataclasses import dataclass, field
from typing import Optional

VALID_CATEGORIES = ("electronics", "groceries", "cleaning", "personal_care", "apparel",
                      "home_tools")

@dataclass
class DealInput:
    title: str
    store: str
    category: str
    url: str
    price: Optional[float] = None
    original_price: Optional[float] = None
    image_url: Optional[str] = None
    source: str = "slickdeals_rss"
    expires_at: Optional[str] = None
    # Fulfillment scope: 'local' (in-store/pickup near ZIP), 'online'
    # (ships anywhere), or 'unknown' (no signal — classified at ingest).
    scope: str = "unknown"

@dataclass
class CouponInput:
    store: str
    code: Optional[str] = None
    description: Optional[str] = None
    promo_link: Optional[str] = None
    deal_hash: Optional[str] = None
    source: str = "store_feed"
    expires_at: Optional[str] = None
