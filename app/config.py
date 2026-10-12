"""Central config — env + defaults per §4/§5 (Zip context: Chesterfield, MO)."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

DATABASE_PATH = Path(os.getenv("DATABASE_PATH", "data/dealhunter.db"))
if not DATABASE_PATH.is_absolute():
    DATABASE_PATH = BASE_DIR / DATABASE_PATH

ZIP_CODE = os.getenv("ZIP_CODE", "63005")
SCRAPE_INTERVAL_MINUTES = int(os.getenv("SCRAPE_INTERVAL_MINUTES", "30"))
ALERT_MIN_DISCOUNT_PCT = float(os.getenv("ALERT_MIN_DISCOUNT_PCT", "20.0"))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

CATEGORIES = ("electronics", "groceries", "cleaning", "personal_care")

WATCHLIST_PATH = BASE_DIR / "config" / "watchlist.json"
SCHEMA_PATH = BASE_DIR / "schema.sql"
