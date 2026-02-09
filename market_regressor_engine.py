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
    print("[START] Market Regressor — Sincronização Forçada")
    print("="*60)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        page = context.new_page()
        
        print("[POLLING] Abrindo página de ofertas...")
        try:
            page.goto("https://www.amazon.com.br/ofertas", wait_until="networkidle", timeout=90000)
            
            # ESPERA CRÍTICA: Aguarda o grid aparecer na tela antes de tentar contar
            print("[INFO] Aguardando elementos renderizarem...")
            page.wait_for_selector("[data-testid='grid-desktop-item']", timeout=30000)
            
            # Dá um scroll para garantir que o 'lazy load' carregue os dados
            page.mouse.wheel(0, 1000)
            page.wait_for_timeout(5000)

            items = page.query_selector_all("[data-testid='grid-desktop-item']")
            print(f"[INFO] Cards detectados: {len(items)}")
            
            found_count = 0
            for item in items:
                try:
                    # Busca o desconto
                    disc_el = item.query_selector("[class*='badge-percent-off'], [class*='savingsPercentage']")
                    if not disc_el: continue
                    discount = int(''.join(filter(str.isdigit, disc_el.inner_text())))

                    if discount >= MIN_DISCOUNT:
                        # Busca título e link
                        link_el = item.query_selector("a[class*='a-link-normal']")
                        title = item.query_selector("span.a-truncate-cut").inner_text().strip()
                        link = link_el.get_attribute("href").split("?")[0]
                        full_link = link if link.startswith("http") else f"https://www.amazon.com.br{link}"
                        
                        price_el = item.query_selector(".a-price-whole")
                        price = f"R$ {price_el.inner_text().strip()}" if price_el else "Confira"

                        prod = {"title": title[:70], "discount": discount, "link": full_link, "price": price}
                        print(f"[SUCCESS] {discount}% OFF - {title[:30]}...")
                        send_to_discord(prod)
                        found_count += 1
                except: continue
                
        except Exception as e:
            print(f"[ERRO] Elementos não apareceram a tempo: {e}")
            page.screenshot(path="timeout_debug.png")
        
        browser.close()
        print(f"[FINISHED] Enviados: {found_count}")

if __name__ == "__main__":
    run()
