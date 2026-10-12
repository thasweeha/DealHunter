# Project Requirements Specification: Automated Multi-Source Deal Hunter & Dynatrace-Style Dashboard

## 1. Executive Summary
The objective of this project is to build an intelligent, automated deal-hunting engine that scans major retailers (Walmart, Target, Aldi, Slickdeals, and coupon aggregators) for high-utility household essentials, groceries, non-expiring personal care items, and electronics. The system will process incoming data, filter it through a user-defined watchlist, search for active coupon codes or digital rebates, trigger instant push notifications via Telegram, and display all active deals in a real-time, pane-based web dashboard inspired by Dynatrace.

---

## 2. Scope & Target Categories
The application will track and categorize deals across four primary domains:
1. **Electronics & Tech Hardware:** Laptops, PCs, monitors, networking gear, and computer components (new, refurbished, open-box).
2. **Groceries & Pantry Staples:** Long-shelf items, coffee, cooking oils, rice, flour, and fresh produce/vegetables.
3. **Household & Cleaning Supplies:** Dishwashing liquid/pods, laundry detergent, trash bags, paper towels, and toilet paper.
4. **Personal Care & Non-Expiring Goods:** Hygiene products, personal care items, and shelf-stable essentials with no immediate expiration date.

---

## 3. Functional Requirements

### 3.1 Data Acquisition & Scraping Layer
* **RSS & Feed Parsing:** Ingest real-time deal streams from Slickdeals and deal aggregator RSS feeds.
* **Retailer Monitoring:** Scrape or fetch promotional data, clearance items, and weekly circular highlights from target stores (Walmart, Target, Aldi) based on local availability (Zip Code context: Chesterfield, MO).
* **Coupon & Promo Code Search:** Automatically query coupon aggregators (e.g., RetailMeNot, Honey, or store-specific coupon feeds) to discover and attach valid coupon codes, promo links, or clipped digital store offers corresponding to the tracked items.

### 3.2 Processing & Filtering Engine
* **Watchlist Matching:** Filter incoming deals against custom keyword lists and synonyms (e.g., "laptop", "dish detergent", "paper towels", "ladies hygiene").
* **Price-per-Unit Normalization:** Where applicable, calculate the unit price (e.g., price per ounce or 100 sheets) to determine if a multi-pack or bulk item is genuinely a lower cost.
* **Deduplication & Storage:** Maintain a local SQLite database to track historical prices, prevent duplicate alerts, and record active deals and associated coupons.

### 3.3 Notification Layer
* **Instant Push Alerts:** Automatically push matching deals that cross a specified discount threshold ($>20\%$ off or historical low) straight to a **Telegram Bot**.
* **Rich Notification Format:** Alerts must include the item title, store name, computed discount, extracted coupon code (if available), and direct purchase link.

### 3.4 Web Dashboard (Dynatrace-Style)
* **Local Web Interface:** Built using a lightweight Python web framework (FastAPI or Flask).
* **Pane-Based Grid Layout:** A sleek, dark-mode technical dashboard mimicking Dynatrace's operational grid view with live status indicators, health pulses, and data streams.
* **Category Panes:** Dedicated visual panes/tiles for:
  * *Electronics*
  * *Groceries & Vegetables*
  * *Cleaning Supplies*
  * *Personal Care & Non-Expiring*
* **Live Features:** Real-time counters showing active deals, coupon availability badges, last scrape timestamps, and quick-filter buttons.

---

## 4. Technical Architecture

```text
+-------------------------------------------------------------------------+
|                              DATA SOURCES                               |
|  [Slickdeals RSS]  [Walmart/Target]  [Aldi Circulars]  [Coupon Sources] |
+------------------------------------+------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
|                         PYTHON BACKEND ENGINE                           |
|  - Scheduler (APScheduler / Background Worker)                          |
|  - Scrapers / API Clients (BeautifulSoup, Feedparser, Playwright)       |
|  - Coupon Matcher & Unit Price Normalizer                               |
|  - SQLite Database (Historical tracking & caching)                      |
+------------------------------------+------------------------------------+
         |                           |                            |
         v                           v                            v
+------------------+       +--------------------+       +-----------------+
| TELEGRAM BOT     |       | WEB DASHBOARD      |       | REST API END    |
| (Instant Alerts) |       | (FastAPI / HTML)   |       | (JSON Endpoints)|
+------------------+       +--------------------+       +-----------------+
```

---

## 5. Proposed Technology Stack
* **Language:** Python 3.x
* **Core Libraries:** 
  * `feedparser` (RSS processing)
  * `BeautifulSoup4` / `Playwright` (Web scraping and circular parsing)
  * `sqlite3` (Lightweight persistence and deduplication)
* **Web Dashboard:** FastAPI with Tailwind CSS (rendered in a single responsive layout file).
* **Notifications:** Telegram Bot HTTP API requests.