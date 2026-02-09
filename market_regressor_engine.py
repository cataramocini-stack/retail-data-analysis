import os
import time
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
import requests

load_dotenv()

# Configurações
DISCORD_WEBHOOK = os.getenv("INGESTION_ENDPOINT_PRIMARY")
AFFILIATE_TAG = os.getenv("AFFILIATION_DATA_METRIC", "scriptoriu01a-20")
MIN_DISCOUNT = 5  # Baixamos para 5% para testar!

def send_to_discord(product):
    payload = {
        "content": f"🚨 **OFERTA ENCONTRADA!**\n📦 **{product['title']}**\n💰 Preço: {product['price']}\n📉 Desconto: {product['discount']}%\n🔗 Link: {product['link']}?tag={AFFILIATE_TAG}"
    }
    requests.post(DISCORD_WEBHOOK, json=payload)

def run():
    print("============================================================")
    print("[START] Market Regressor — Mira Calibrada")
    print("============================================================")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        page = context.new_page()
        
        print(f"[POLLING] Acessando Amazon Ofertas...")
        page.goto("https://www.amazon.com.br/ofertas", wait_until="networkidle")
        
        # Espera os cards de produtos carregarem
        page.wait_for_timeout(5000)
        
        # Tenta capturar os produtos pelos seletores mais comuns
        products = page.query_selector_all("[data-testid='grid-desktop-item']")
        
        found_any = False
        for item in products:
            try:
                title = item.query_selector(".a-truncate-cut").inner_text()
                # Pega o desconto (ex: "20% off")
                discount_text = item.query_selector("[class*='badge-percent-off']").inner_text()
                discount_val = int(''.join(filter(str.isdigit, discount_text)))
                
                if discount_val >= MIN_DISCOUNT:
                    link = item.query_selector("a").get_attribute("href").split("?")[0]
                    price = item.query_selector(".a-price-whole").inner_text()
                    
                    product_data = {
                        "title": title,
                        "price": f"R$ {price}",
                        "discount": discount_val,
                        "link": link if link.startswith("http") else f"https://www.amazon.com.br{link}"
                    }
                    
                    print(f"[SUCCESS] {title} - {discount_val}% OFF")
                    send_to_discord(product_data)
                    found_any = True
            except:
                continue
        
        if not found_any:
            print("[INFO] Nenhuma oferta acima do filtro foi encontrada nesta rodada.")
            # Tira print da tela para debug (ajuda a ver se deu Captcha)
            page.screenshot(path="debug.png")
            
        browser.close()

if __name__ == "__main__":
    run()
