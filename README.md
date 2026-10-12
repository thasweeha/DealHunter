# DealHunter

An automated multi-source deal-hunting engine. It scans major retailers and deal
aggregators for household essentials, groceries, personal care, apparel, and
electronics, matches them against your watchlist, finds coupon signals, and shows
everything on a live dashboard — with Telegram push alerts for hot deals.

## Features

- **Multi-source ingest**: Slickdeals (Playwright), Reddit deal subs, 9to5Toys,
  Hip2Save, DealNews, Spoofee, DansDeals, Doctor of Credit, DealMania, Dell,
  Lenovo, Newegg, and ALDI Finds — plus optional SerpApi, Takeads, and Strackr
- **Smart filtering**: keyword/synonym watchlist, 20% discount gate, price-per-unit
  normalization, historical-low tracking, SHA dedup, 7-day stale-link pruning
- **Coupons**: promo-code, clippable-coupon, rebate, and BOGO signals attached to deals
- **Dashboard**: category panes (Electronics, Groceries, Cleaning, Personal Care,
  Apparel, Home & Tools) split into Near-ZIP and Online halves, with retailer
  filter, sorting, search, coupon-only toggle, and editable ZIP
- **Alerts**: Telegram bot pushes (title, store, discount, coupon, buy link)

## Quickstart (Windows)

```powershell
# 1. Python 3.12+ required (winget install Python.Python.3.12)
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\playwright install chromium

# 2. Configure
copy .env.example .env   # fill TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID (optional)

# 3. Run (scans immediately, then every 30 min)
.\.venv\Scripts\uvicorn app.main:app --reload
# open http://127.0.0.1:8000
```

Linux/macOS: replace `.venv\Scripts\` with `.venv/bin/` and `copy` with `cp`.

## Configuration

| Setting | Where | Default |
|---|---|---|
| ZIP code | Dashboard filter bar or `ZIP_CODE` in `.env` | `63005` (Chesterfield, MO) |
| Scan interval | `SCRAPE_INTERVAL_MINUTES` in `.env` | `30` |
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | off until set |
| Provider keys | Dashboard → API keys, or `SERPAPI_KEY` / `TAKEADS_KEY` / `STRACKR_KEY` | off until set |

Watchlist keywords live in `config/watchlist.json` and merge into the DB on startup.

## API

- `GET /` — dashboard
- `GET /api/deals?category=&store=&coupon_only=&scope=local|online`
- `GET /api/coupons`, `GET /api/stats` (includes scheduler health)
- `POST /api/scan` — trigger a full scan
- `GET/POST /api/settings/zip`, `GET/POST /api/settings/keys`

## Notes

- SQLite (`data/dealhunter.db`, git-ignored) is the entire database.
- Retailer direct sites (Walmart/Target/Aldi/Costco) aggressively block bots, so
  those deals arrive via aggregators; each card has a merchant search link.
- Reddit throttles aggressive polling — the scanner backs off politely on HTTP 429.
