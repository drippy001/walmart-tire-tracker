import os
import json
import re
import requests
from playwright.sync_api import sync_playwright

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
STATE_FILE = "tire_data.json"

# --- CONFIGURATION ---
TIRE_SIZE = "235/45R18"
TARGET_PRICE = 150  # Set your "good deal" price here (e.g., $150)
WALMART_SEARCH_URL = f"https://www.walmart.com/search?q={TIRE_SIZE.replace('/', '%2F')}"

def send_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=10)

def check_prices():
    with sync_playwright() as p:
        # Using a realistic user-agent helps avoid simple bot blocks
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        page = context.new_page()
        
        try:
            page.goto(WALMART_SEARCH_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)  # Wait 5 seconds for dynamic content to load
            
            # Extract product titles and prices. Selectors may need updating if Walmart changes their site.
            # Common selectors for Walmart: [data-testid="price"], .price-characteristic, [data-automation-id="product-price"]
            products = page.query_selector_all('div[data-item-id]')  # Each product card typically has this attribute
            
            previous_data = load_state()
            alerts = []
            current_prices = {}

            for product in products:
                try:
                    title_elem = product.query_selector('span[data-automation-id="product-title"]')
                    price_elem = product.query_selector('[data-testid="price"], .price-characteristic, [data-automation-id="product-price"]')
                    
                    if title_elem and price_elem:
                        title = title_elem.inner_text().strip()
                        price_text = price_elem.inner_text().strip()
                        # Extract numeric price (e.g., "$130.00" -> 130.0)
                        price_match = re.search(r'[\d,]+\.?\d*', price_text.replace('$', '').replace(',', ''))
                        if price_match:
                            current_price = float(price_match.group())
                            current_prices[title] = current_price
                            
                            # Check if it's a good deal
                            if current_price <= TARGET_PRICE:
                                old_price = previous_data.get(title)
                                if old_price != current_price:  # Avoid duplicate alerts
                                    alerts.append(f"🚨 TIRE DEAL: {title} is now ${current_price:.2f}!\nCheck it here: {WALMART_SEARCH_URL}")
                except Exception as e:
                    print(f"Error parsing a product: {e}")
                    continue

            # Save the new prices for the next run
            save_state(current_prices)
            
            # Send alerts
            for alert in alerts:
                send_telegram(alert)
                
            if not alerts:
                print(f"Checked {len(current_prices)} tires. No deals below ${TARGET_PRICE} found.")

        except Exception as e:
            print(f"Error loading Walmart page: {e}")
            
        browser.close()

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

if __name__ == "__main__":
    check_prices()
