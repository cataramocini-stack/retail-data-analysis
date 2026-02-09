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
    print("[START] Market Regressor — Camuflagem Ativada")
    print("="*60)
    with sync_playwright() as p:
        # Lançamos com argumentos que escondem o fato de ser automação
        browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
        )
        page = context.new_page()
        
        print("[POLLING] Tentando acessar Amazon (Modo Furtivo)...")
        try:
            # Vamos para a home primeiro para criar um 'rastro' humano
            page.goto("https://www.amazon.com.br", wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            
            # Agora sim vamos para as ofertas
            page.goto("https://www.amazon.com.br/gp/goldbox", wait_until="domcontentloaded")
            page.wait_for_timeout(10000)
            
            # Novo seletor mais abrangente
            items = page.query_selector_all("[data-testid='grid-desktop-item'], .dealContainer")
            print(f"[INFO] Itens detectados: {len(items)}")
            
            # Se não detectar nada, tira foto pra gente ver o bloqueio
            if len(items) == 0:
                page.screenshot(path="bloqueio.png")
                print("[!] Bloqueio detectado. Foto 'bloqueio.png' salva.")

            for item in items:
                try:
                    title_el = item.query_selector(".a-truncate-cut, h3, [class*='dealTitleText']")
                    title = title_el.inner_text().strip()
                    
                    disc_el = item.query_selector("[class*='badge-percent-off'], [class*='savingsPercentage']")
                    if not disc_el: continue
                    
                    discount = int(''.join(filter(str.isdigit, disc_el.inner_text())))
                    
                    if discount >= MIN_DISCOUNT:
                        link_el = item.query_selector("a")
                        link = link_el.get_attribute("href").split("?")[0]
                        full_link = link if link.startswith("http") else f"https://www.amazon.com.br{link}"
                        
                        prod = {"title": title[:60], "discount": discount, "link": full_link, "price": "Confira!"}
                        print(f"[SUCCESS] {discount}% OFF - {title[:30]}...")
                        send_to_discord(prod)
                except: continue
        except Exception as e:
            print(f"[ERRO] {e}")
        
        browser.close()
        print("[FINISHED]")

if __name__ == "__main__":
    run()
