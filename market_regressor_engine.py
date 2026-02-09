import os
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
import requests

load_dotenv()

DISCORD_WEBHOOK = os.getenv("INGESTION_ENDPOINT_PRIMARY")
AFFILIATE_TAG = "gabriel01-20" # Tag genérica para teste

def send_to_discord(product):
    payload = {"content": f"🔥 **OFERTA NO MERCADO LIVRE!**\n📦 **{product['title']}**\n💰 Preço: {product['price']}\n📉 Desconto: {product['discount']}\n🔗 {product['link']}"}
    try: requests.post(DISCORD_WEBHOOK, json=payload)
    except: pass

def run():
    print("="*60)
    print("[START] Market Regressor — Teste Mercado Livre")
    print("="*60)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        page = context.new_page()
        
        print("[POLLING] Acessando Ofertas do Dia (Mercado Livre)...")
        try:
            # ML é mais rápido e não bloqueia tanto IP de data center
            page.goto("https://www.mercadolivre.com.br/ofertas", wait_until="domcontentloaded")
            page.wait_for_selector(".promotion-item", timeout=20000)
            
            items = page.query_selector_all(".promotion-item")
            print(f"[INFO] Itens detectados: {len(items)}")
            
            found_count = 0
            for item in items:
                try:
                    title = item.query_selector(".promotion-item__title").inner_text().strip()
                    price = item.query_selector(".andes-money-amount__fraction").inner_text().strip()
                    discount = item.query_selector(".promotion-item__discount-text").inner_text().strip()
                    link = item.query_selector("a").get_attribute("href")
                    
                    prod = {"title": title[:70], "price": f"R$ {price}", "discount": discount, "link": link}
                    print(f"[SUCCESS] {discount} OFF - {title[:30]}")
                    send_to_discord(prod)
                    found_count += 1
                    if found_count >= 5: break # Pegar só 5 para testar
                except: continue
                
            print(f"[FINISHED] Enviados: {found_count}")
        except Exception as e:
            print(f"[ERRO] Mercado Livre também bloqueou: {e}")
        
        browser.close()

if __name__ == "__main__":
    run()
