import os
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
import requests

load_dotenv()

DISCORD_WEBHOOK = os.getenv("INGESTION_ENDPOINT_PRIMARY")
AFFILIATE_TAG = os.getenv("AFFILIATION_DATA_METRIC", "scriptoriu01a-20")
MIN_DISCOUNT = 5

def send_to_discord(product):
    payload = {"content": f"🚨 **OFERTA!** {product['discount']}% OFF\n📦 **{product['title']}**\n💰 {product['price']}\n🔗 {product['link']}?tag={AFFILIATE_TAG}"}
    try: requests.post(DISCORD_WEBHOOK, json=payload)
    except: pass

def run():
    print("="*60)
    print("[START] Market Regressor — Bug Fix Final")
    print("="*60)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        page = context.new_page()
        page.set_default_timeout(90000)
        
        print("[POLLING] Acessando Amazon...")
        try:
            page.goto("https://www.amazon.com.br/ofertas", wait_until="domcontentloaded")
            page.wait_for_timeout(10000)
            
            # Captura os cards de produtos
            items = page.query_selector_all("[data-testid='grid-desktop-item']")
            print(f"[INFO] Itens detectados: {len(items)}")
            
            for item in items:
                try:
                    title = item.query_selector(".a-truncate-cut").inner_text().strip()
                    disc_el = item.query_selector("[class*='badge-percent-off']")
                    if not disc_el: continue
                    
                    discount = int(''.join(filter(str.isdigit, disc_el.inner_text())))
                    
                    if discount >= MIN_DISCOUNT:
                        link = item.query_selector("a").get_attribute("href").split("?")[0]
                        full_link = link if link.startswith("http") else f"https://www.amazon.com.br{link}"
                        
                        prod = {"title": title[:50], "discount": discount, "link": full_link, "price": "Confira no link"}
                        print(f"[SUCCESS] Encontrado: {discount}% OFF")
                        send_to_discord(prod)
                except: continue
        except Exception as e:
            print(f"[ERRO] {e}")
        browser.close()
        print("[FINISHED]")

if __name__ == "__main__":
    run()
