import os
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
import requests

load_dotenv()
DISCORD_WEBHOOK = os.getenv("INGESTION_ENDPOINT_PRIMARY")
AFFILIATE_TAG = os.getenv("AFFILIATION_DATA_METRIC", "scriptoriu01a-20")

def send_to_discord(product):
    payload = {"content": f"🚨 **OFERTA DETECTADA!**\n📦 **{product['title']}**\n📉 Desconto: {product['discount']}\n💰 Preço: {product['price']}\n🔗 {product['link']}?tag={AFFILIATE_TAG}"}
    try: requests.post(DISCORD_WEBHOOK, json=payload)
    except: pass

def run():
    print("="*60)
    print("[START] Market Regressor — Amazon Recon")
    print("="*60)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        print("[POLLING] Entrando na Amazon...")
        try:
            # Indo para a página de ofertas
            page.goto("https://www.amazon.com.br/ofertas", wait_until="domcontentloaded")
            
            # Espera 10 segundos e rola um pouco (simulando humano)
            page.wait_for_timeout(10000)
            page.mouse.wheel(0, 500)
            
            # Em vez de buscar o 'grid' (que ela esconde), vamos buscar todos os links de produtos
            # Na Amazon, produtos geralmente têm '/dp/' no link
            links = page.query_selector_all("a[href*='/dp/']")
            print(f"[INFO] Links de produtos encontrados: {len(links)}")
            
            found_count = 0
            for link_el in links:
                try:
                    title = link_el.inner_text().strip()
                    # Se o título for muito curto ou vazio, pula
                    if len(title) < 20: continue 
                    
                    href = link_el.get_attribute("href")
                    full_link = href.split("?")[0]
                    if not full_link.startswith("http"):
                        full_link = f"https://www.amazon.com.br{full_link}"
                    
                    # Tenta achar o desconto no texto ao redor
                    parent_text = link_el.evaluate("el => el.parentElement.innerText")
                    
                    # Se tiver '%' ou 'off', é uma oferta!
                    if "%" in parent_text:
                        print(f"[SUCCESS] Oferta encontrada: {title[:40]}...")
                        send_to_discord({
                            "title": title[:100],
                            "discount": "Ver no link",
                            "price": "Em oferta",
                            "link": full_link
                        })
                        found_count += 1
                        if found_count >= 5: break
                except: continue

            if found_count == 0:
                print("[!] Nenhum item com '%' encontrado nos links.")
                page.screenshot(path="amazon_final_check.png")

        except Exception as e:
            print(f"[ERRO] {e}")
        
        browser.close()
        print(f"[FINISHED] Itens enviados: {found_count}")

if __name__ == "__main__":
    run()
