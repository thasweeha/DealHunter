"""Price-per-unit normalization (§3.2): price / quantity for bulk comparison."""
import re

_QTY_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(oz|lb|lbs|ml|l|g|kg|ct|count|sheets|pods|rolls)\b", re.I)

UNIT_TO_BASE = {"lbs": "lb"}

def parse_quantity(title: str) -> tuple[float | None, str | None]:
    """Extract (qty, unit) e.g. 'Paper Towels 12 Rolls' -> (12, 'rolls')."""
    if not title:
        return None, None
    m = _QTY_RE.search(title)
    if not m:
        # fallback: pack count like '12-pack', '6 count'
        m2 = re.search(r"(\d+)\s*[- ]?(pack|count|ct)\b", title, re.I)
        if m2:
            return float(m2.group(1)), "count"
        return None, None
    qty, unit = float(m.group(1)), m.group(2).lower()
    return qty, UNIT_TO_BASE.get(unit, unit)

def compute_unit_price(price: float | None, title: str) -> tuple[float | None, str | None]:
    if not price or price <= 0:
        return None, None
    qty, unit = parse_quantity(title)
    if not qty:
        return None, None
    return round(price / qty, 4), unit

def compute_discount_pct(price: float | None, original_price: float | None) -> float | None:
    if not price or not original_price or original_price <= 0:
        return None
    if price >= original_price:
        return 0.0
    return round((original_price - price) / original_price * 100, 2)
