import os
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
import requests

load_dotenv()

DISCORD_WEBHOOK = os.getenv("INGESTION_ENDPOINT_PRIMARY")
AFFILIATE_TAG = os.getenv("AFFILIATION_DATA_METRIC", "scriptoriu01a-20")
MIN_DISCOUNT = 5

def send_to_discord(product):
    payload = {"content": f"🚨 **OFERTA ENCONTRADA!**\n📦 **{product['title']}**\n💰 Preço: {product['price']}\n📉 Desconto: {product['discount']}%\n🔗 Link: {product['link']}?tag={AFFILIATE_TAG}"}
    try: requests.post(DISCORD_WEBHOOK, json=payload)
    except: pass

def run():
    print("="*60)
    print("[START] Market Regressor — Ajuste de Grid Detectado")
    print("="*60)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        page = context.new_page()
        
        print("[POLLING] Acessando a vitrine de ofertas...")
        try:
            # Acessando a URL exata da sua foto
            page.goto("https://www.amazon.com.br/ofertas", wait_until="domcontentloaded")
            page.wait_for_timeout(10000) # Tempo para carregar os cards da imagem
            
            # Novo seletor baseado no grid da sua imagem
            items = page.query_selector_all("[data-testid='grid-desktop-item']")
            print(f"[INFO] Itens detectados no grid: {len(items)}")
            
            for item in items:
                try:
                    # Título: Na foto, ele usa uma classe de truncamento
                    title_el = item.query_selector("a[class*='a-link-normal'] span, [class*='Title']")
                    title = title_el.inner_text().strip() if title_el else "Produto sem título"
                    
                    # Desconto: O selo vermelho "X% off" na foto
                    disc_el = item.query_selector("[class*='badge-percent-off'], [class*='savingsPercentage']")
                    if not disc_el: continue
                    
                    discount = int(''.join(filter(str.isdigit, disc_el.inner_text())))
                    
                    if discount >= MIN_DISCOUNT:
                        link_el = item.query_selector("a[class*='a-link-normal']")
                        link = link_el.get_attribute("href").split("?")[0]
                        full_link = link if link.startswith("http") else f"https://www.amazon.com.br{link}"
                        
                        # Preço: Pegando a parte inteira (ex: R$ 174)
                        price_el = item.query_selector(".a-price-whole")
                        price = price_el.inner_text().strip() if price_el else "Ver no site"
                        
                        prod = {"title": title[:60], "discount": discount, "link": full_link, "price": f"R$ {price}"}
                        print(f"[SUCCESS] {discount}% OFF - {title[:30]}...")
                        send_to_discord(prod)
                except: continue
        except Exception as e:
            print(f"[ERRO] {e}")
        
        browser.close()
        print("[FINISHED]")

if __name__ == "__main__":
    run()
