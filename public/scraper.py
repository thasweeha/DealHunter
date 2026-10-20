import feedparser
import json
import re

# 1. Permanent Curated Major Retailer Deal Hubs (Always available)
curated_retailer_deals = [
    {
        "id": 1001,
        "title": "Aldi Weekly Finds – Seasonal Groceries & Home Goods",
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
        "title": "Walmart Deals & Rollbacks – Everyday Low Prices",
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
        "title": "Target Circle Deals & Weekly Ad Savings",
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
        "title": "Amazon Today's Goldbox Deals & Lightning Offers",
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
        "title": "Costco Online Offers & Member Savings",
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
        "title": "The Home Depot Special Buys & Savings Center",
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
        "title": "Newegg Shell Shocker & PC Component Deals",
        "store": "Newegg",
        "url": "https://www.newegg.com/todays-deals",
        "image": "https://images.unsplash.com/photo-1587202372775-e229f172b9d7?auto=format&fit=crop&w=600&q=80",
        "category": "electronics",
        "coupon": "Shell Shocker",
        "zip_code": "",
        "online": True
    }
]

# 2. Live RSS Feeds Scraper
RSS_FEEDS = [
    "https://slickdeals.net/newsearch.php?mode=frontpage&searcharea=deals&searchin=first&rss=1",
    "https://www.dealsofamerica.com/arss.xml"
]

all_deals = list(curated_retailer_deals) # Start with curated major stores
deal_id = 2000

# Variety of professional image placeholders to prevent identical thumbnails
fallback_images = [
    "https://images.unsplash.com/photo-1526738549149-8e07eca6c147?auto=format&fit=crop&w=600&q=80",
    "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?auto=format&fit=crop&w=600&q=80",
    "https://images.unsplash.com/photo-1523275335684-37898b6baf30?auto=format&fit=crop&w=600&q=80",
    "https://images.unsplash.com/photo-1546868871-7041f2a55e12?auto=format&fit=crop&w=600&q=80"
]

for feed_url in RSS_FEEDS:
    parsed_feed = feedparser.parse(feed_url)
    for index, entry in enumerate(parsed_feed.entries):
        # Extract image if present, otherwise cycle through varied fallback images
        image_url = fallback_images[index % len(fallback_images)]
        if hasattr(entry, 'summary'):
            img_match = re.search(r'src="([^"]+)"', entry.summary)
            if img_match:
                image_url = img_match.group(1)

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

        # Assign local ZIP to some live items to showcase local vs online filtering
        is_local = (deal_id % 4 == 0)
        zip_code = "63017" if is_local else ""

        deal = {
            "id": deal_id,
            "title": title,
            "store": store,
            "url": entry.get("link", "#"),
            "image": image_url,
            "category": "electronics",
            "coupon": badge,
            "zip_code": zip_code,
            "online": not is_local
        }
        all_deals.append(deal)
        deal_id += 1

# Save consolidated database
with open("deals.json", "w") as f:
    json.dump(all_deals, f, indent=4)

print(f"Successfully consolidated {len(all_deals)} deals (including major US retailer hubs) into deals.json.")