import feedparser
import json
import html
import re
import os

# 1. Curated Major US Retailer Hubs
curated_retailer_deals = [
    {
        "id": 1001,
        "title": "Aldi Weekly Finds – Seasonal Groceries & Kitchen Gadgets",
        "store": "Aldi",
        "url": "https://www.aldi.us/en/weekly-finds/",
        "image": "https://images.unsplash.com/photo-1556911220-e15b29be8c8f?auto=format&fit=crop&w=600&q=80",
        "category": "groceries",
        "coupon": "In-Store Hub",
        "zip_code": "63017",
        "online": False
    },
    {
        "id": 1002,
        "title": "Best Buy Top Deals – TVs, Laptops & Electronics Clearance",
        "store": "BestBuy",
        "url": "https://www.bestbuy.com/site/clp/top-deals/pcmcat1560960572173.c",
        "image": "https://images.unsplash.com/photo-1593359677879-a4bb92f829d1?auto=format&fit=crop&w=600&q=80",
        "category": "electronics",
        "coupon": "Top Deals",
        "zip_code": "",
        "online": True
    },
    {
        "id": 1003,
        "title": "Walmart Deals & Rollbacks – Everyday Savings",
        "store": "Walmart",
        "url": "https://www.walmart.com/tp/deals",
        "image": "https://images.unsplash.com/photo-1517668808822-9ebb02f2a0e6?auto=format&fit=crop&w=600&q=80",
        "category": "home",
        "coupon": "Rollback",
        "zip_code": "63017",
        "online": True
    },
    {
        "id": 1004,
        "title": "Target Circle Deals & Weekly Ad Specials",
        "store": "Target",
        "url": "https://www.target.com/c/target-circle-deals/-/N-5xsxf",
        "image": "https://images.unsplash.com/photo-1588854337236-6889d631faa8?auto=format&fit=crop&w=600&q=80",
        "category": "home",
        "coupon": "Circle Deal",
        "zip_code": "63017",
        "online": True
    },
    {
        "id": 1005,
        "title": "Amazon Today's Deals & Lightning Offers",
        "store": "Amazon",
        "url": "https://www.amazon.com/gp/goldbox",
        "image": "https://images.unsplash.com/photo-1558002038-1055907df827?auto=format&fit=crop&w=600&q=80",
        "category": "electronics",
        "coupon": "Goldbox",
        "zip_code": "",
        "online": True
    },
    {
        "id": 1006,
        "title": "Costco Member Savings & Online Warehouse Offers",
        "store": "Costco",
        "url": "https://www.costco.com/online-offers.html",
        "image": "https://images.unsplash.com/photo-1571175337573-45bc5eb92af5?auto=format&fit=crop&w=600&q=80",
        "category": "groceries",
        "coupon": "Member Only",
        "zip_code": "63017",
        "online": True
    },
    {
        "id": 1007,
        "title": "The Home Depot Special Buys & Tool Center",
        "store": "HomeDepot",
        "url": "https://www.homedepot.com/b/Special-Buys/N-5yc1vZarqq",
        "image": "https://images.unsplash.com/photo-1504148455328-c376907d081c?auto=format&fit=crop&w=600&q=80",
        "category": "tools",
        "coupon": "Special Buy",
        "zip_code": "63017",
        "online": False
    },
    {
        "id": 1008,
        "title": "Newegg Shell Shocker & Hardware Savings",
        "store": "Newegg",
        "url": "https://www.newegg.com/todays-deals",
        "image": "https://images.unsplash.com/photo-1587202372775-e229f172b9d7?auto=format&fit=crop&w=600&q=80",
        "category": "electronics",
        "coupon": "Shell Shocker",
        "zip_code": "",
        "online": True
    }
]

# 2. RSS Sources
RSS_FEEDS = [
    "https://slickdeals.net/newsearch.php?mode=frontpage&searcharea=deals&searchin=first&rss=1",
    "https://www.dealsofamerica.com/arss.xml"
]

def extract_image_url(entry, title=""):
    """Extracts actual deal thumbnail from Media RSS, enclosures, or HTML."""
    # Media RSS tags
    if "media_thumbnail" in entry and len(entry.media_thumbnail) > 0:
        return entry.media_thumbnail[0].get("url")
    if "media_content" in entry and len(entry.media_content) > 0:
        return entry.media_content[0].get("url")

    # RSS enclosure tags
    if "enclosures" in entry and len(entry.enclosures) > 0:
        enc_url = entry.enclosures[0].get("href") or entry.enclosures[0].get("url")
        if enc_url and any(enc_url.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp"]):
            return enc_url

    # HTML body search
    html_corpus = ""
    if hasattr(entry, "summary"):
        html_corpus += entry.summary
    if hasattr(entry, "description"):
        html_corpus += " " + entry.description
    if "content" in entry and len(entry.content) > 0:
        html_corpus += " " + entry.content[0].get("value", "")

    if html_corpus:
        clean_html = html.unescape(html_corpus)
        match = re.search(r'<img[^>]+src=[\'"]([^\'"]+)[\'"]', clean_html, re.IGNORECASE)
        if match:
            found_url = match.group(1)
            if not any(px in found_url.lower() for px in ["1x1", "pixel", "beacon", "clear.gif"]):
                return found_url

    # Fallback images matching title keywords
    t = title.lower()
    if any(k in t for k in ["tv", "oled", "monitor", "soundbar", "speaker"]):
        return "https://images.unsplash.com/photo-1593359677879-a4bb92f829d1?auto=format&fit=crop&w=600&q=80"
    elif any(k in t for k in ["drill", "tool", "saw", "cordless", "wrench", "pliers"]):
        return "https://images.unsplash.com/photo-1504148455328-c376907d081c?auto=format&fit=crop&w=600&q=80"
    elif any(k in t for k in ["cook", "kitchen", "coffee", "fryer", "snack", "food", "table"]):
        return "https://images.unsplash.com/photo-1556911220-e15b29be8c8f?auto=format&fit=crop&w=600&q=80"
    elif any(k in t for k in ["laptop", "pc", "gpu", "usb", "charger", "ssd", "ram", "phone", "apple"]):
        return "https://images.unsplash.com/photo-1587202372775-e229f172b9d7?auto=format&fit=crop&w=600&q=80"
    elif any(k in t for k in ["shirt", "pants", "shoe", "hoodie", "cardigan", "jogger", "boot", "socks"]):
        return "https://images.unsplash.com/photo-1523381210434-271e8be1f52b?auto=format&fit=crop&w=600&q=80"
    
    return "https://images.unsplash.com/photo-1607082348824-0a96f2a4b9da?auto=format&fit=crop&w=600&q=80"

all_deals = list(curated_retailer_deals)
deal_id = 2000

for feed_url in RSS_FEEDS:
    parsed_feed = feedparser.parse(feed_url)
    for entry in parsed_feed.entries:
        title = entry.get("title", "Active Offer")
        store = entry.get("author", "Verified Retailer")
        
        badge = "Hot Deal"
        lower_title = title.lower()
        if "clearance" in lower_title:
            badge = "Clearance"
        elif "rollback" in lower_title:
            badge = "Rollback"
        elif "coupon" in lower_title or "off" in lower_title:
            badge = "Coupon"
        elif "free" in lower_title:
            badge = "Freebie"

        is_local = (deal_id % 4 == 0)
        zip_code = "63017" if is_local else ""

        deal = {
            "id": deal_id,
            "title": title,
            "store": store,
            "url": entry.get("link", "#"),
            "image": extract_image_url(entry, title=title),
            "category": "electronics",
            "coupon": badge,
            "zip_code": zip_code,
            "online": not is_local
        }
        all_deals.append(deal)
        deal_id += 1

# Output file path resolution: writes to public/deals.json whether run from root or public folder
current_dir = os.path.dirname(os.path.abspath(__file__))
output_file = os.path.join(current_dir, "deals.json")

with open(output_file, "w") as f:
    json.dump(all_deals, f, indent=4)

print(f"Successfully scraped {len(all_deals)} total deals into {output_file}.")