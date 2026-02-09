import os
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
import requests

load_dotenv()

DISCORD_WEBHOOK = os.getenv("INGESTION_ENDPOINT_PRIMARY")
AFFILIATE_TAG = os.getenv("AFFILIATION_DATA_METRIC", "scriptoriu01a-20")
MIN_DISCOUNT = 5

def send_to_discord(product):
    payload = {"content": f"🚨 **OFERTA ENCONTRADA!**\n📦 **{product['title']}**\n💰 Preço: {product['price']}\n📉 Desconto: {product['discount']}%\n🔗 {product['link']}?tag={AFFILIATE_TAG}"}
    try: requests.post(DISCORD_WEBHOOK, json=payload)
    except: pass

def run():
    print("="*60)
    print("[START] Market Regressor — Calibragem por Imagem")
    print("="*60)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        page = context.new_page()
        
        print("[POLLING] Acessando vitrine de ofertas...")
        try:
            page.goto("https://www.amazon.com.br/ofertas", wait_until="load")
            page.wait_for_timeout(10000) # Tempo para carregar os cards da imagem

            # Pega todos os cards que vimos na sua foto
            items = page.query_selector_all("[data-testid='grid-desktop-item']")
            print(f"[INFO] Cards detectados: {len(items)}")
            
            found_count = 0
            for item in items:
                try:
                    # 1. Busca o desconto (o selo vermelho 'off' da foto)
                    disc_el = item.query_selector("[class*='badge-percent-off'], [class*='savingsPercentage']")
                    if not disc_el: continue
                    discount = int(''.join(filter(str.isdigit, disc_el.inner_text())))

                    if discount >= MIN_DISCOUNT:
                        # 2. Busca o título (o link logo abaixo do preço)
                        title_el = item.query_selector("a span.a-truncate-cut, h3")
                        title = title_el.inner_text().strip() if title_el else "Produto em Oferta"
                        
                        # 3. Busca o link
                        link_el = item.query_selector("a")
                        link = link_el.get_attribute("href").split("?")[0]
                        full_link = link if link.startswith("http") else f"https://www.amazon.com.br{link}"
                        
                        # 4. Busca o preço
                        price_el = item.query_selector(".a-price-whole")
                        price = f"R$ {price_el.inner_text().strip()}" if price_el else "Confira no site"

                        prod = {"title": title[:70], "discount": discount, "link": full_link, "price": price}
                        print(f"[SUCCESS] {discount}% OFF - {title[:30]}...")
                        send_to_discord(prod)
                        found_count += 1
                except: continue
                
        except Exception as e:
            print(f"[ERRO] {e}")
        
        browser.close()
        print(f"[FINISHED] Itens enviados nesta rodada: {found_count}")

if __name__ == "__main__":
    run()
