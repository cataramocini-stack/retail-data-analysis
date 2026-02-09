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
    print("[START] Market Regressor — Teste de Carregamento Forçado")
    print("="*60)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        page = context.new_page()
        
        print("[POLLING] Abrindo Amazon...")
        try:
            page.goto("https://www.amazon.com.br/ofertas", wait_until="load", timeout=90000)
            
            # AJUSTE CHAVE: Espera o elemento do grid aparecer fisicamente na página
            print("[INFO] Aguardando o grid de produtos aparecer...")
            try:
                page.wait_for_selector("[data-testid='grid-desktop-item']", timeout=20000)
            except:
                print("[AVISO] Grid padrão não apareceu, tentando ler o que tem disponível...")

            # Rola a página para baixo para carregar o "lazy load"
            page.evaluate("window.scrollBy(0, 800)")
            page.wait_for_timeout(3000)
            
            # Captura tudo que parece um item de oferta
            items = page.query_selector_all("[data-testid='grid-desktop-item'], [class*='DealGridItem'], .a-section.list-item")
            print(f"[INFO] Itens detectados: {len(items)}")
            
            for item in items:
                try:
                    # Tenta pegar o título de várias formas
                    title_el = item.query_selector(".a-truncate-cut, h3, [class*='dealTitleText'], a span")
                    if not title_el: continue
                    title = title_el.inner_text().strip()
                    
                    # Procura o desconto
                    disc_el = item.query_selector("[class*='badge-percent-off'], [class*='savingsPercentage'], .a-badge-text")
                    if not disc_el: continue
                    
                    discount = int(''.join(filter(str.isdigit, disc_el.inner_text())))
                    
                    if discount >= MIN_DISCOUNT:
                        link_el = item.query_selector("a")
                        link = link_el.get_attribute("href").split("?")[0]
                        full_link = link if link.startswith("http") else f"https://www.amazon.com.br{link}"
                        
                        prod = {"title": title[:60], "discount": discount, "link": full_link, "price": "Confira no link"}
                        print(f"[SUCCESS] {discount}% OFF - {title[:30]}")
                        send_to_discord(prod)
                except: continue
        except Exception as e:
            print(f"[ERRO] {e}")
        
        browser.close()
        print("[FINISHED]")

if __name__ == "__main__":
    run()
