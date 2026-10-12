"""Telegram instant push alerts (§3.3): rich format with coupon + purchase link."""
import requests
from .. import config

def format_message(title: str, store: str, discount_pct, coupon_code, url: str) -> str:
    disc = f"{discount_pct:.1f}% off" if discount_pct is not None else "deal"
    coupon = f"\n🏷️ Coupon: <code>{coupon_code}</code>" if coupon_code else ""
    return (
        f"🔥 <b>{title}</b>\n"
        f"🏪 {store} — <b>{disc}</b>{coupon}\n"
        f"🔗 <a href=\"{url}\">Buy now</a>"
    )

def send_alert(title: str, store: str, discount_pct, coupon_code, url: str) -> bool:
    """POST to Telegram Bot API. Returns True on success; False if unconfigured."""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return False
    api = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    resp = requests.post(api, json={
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": format_message(title, store, discount_pct, coupon_code, url),
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }, timeout=15)
    return resp.ok
