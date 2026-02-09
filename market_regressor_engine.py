import os
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
import requests

load_dotenv()

DISCORD_WEBHOOK = os.getenv("INGESTION_ENDPOINT_PRIMARY")
AFFILIATE_TAG = os.getenv("AFFILIATION_DATA_METRIC", "scriptoriu01a-20")

def send_to_discord(product):
    payload = {"content": f"🚨 **OFERTA ENCONTRADA!**\n📦 **{product['title']}**\n💰 Preço: {product['price']}\n📉 Desconto: {product['discount']}%\n🔗 {product['link']}?tag={AFFILIATE_TAG}"}
    try: requests.post(DISCORD_WEBHOOK, json=payload)
    except: pass

def run():
    print("="*60)
    print("[START] Market Regressor — Modo Ultra Stealth")
    print("="*60)
    with sync_playwright() as p:
        # Mudança chave: Lançamos o Chromium com flags que escondem o WebDriver
        browser = p.chromium.launch(headless=True)
        
        # Criamos um contexto com uma resolução de tela comum e User-Agent atualizado
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 720}
        )
        page = context.new_page()
        
        # Vamos usar a URL de promoções diretas (menos scripts que a página de 'ofertas' geral)
        target_url = "https://www.amazon.com.br/gp/goldbox?ref_=nav_cs_gb"
        
        print(f"[POLLING] Acessando: {target_url}")
        try:
            # Esperamos o carregamento básico
            page.goto(target_url, wait_until="commit", timeout=90000)
            
            # Simulamos um humano esperando e rolando a página
            print("[INFO] Estabilizando página...")
            page.wait_for_timeout(7000)
            page.mouse.wheel(0, 500)
            page.wait_for_timeout(3000)

            # Tentamos capturar os links de produtos que contêm a palavra "deal" ou "offer"
            # Esse seletor é mais robusto para o que vimos na sua foto
            links = page.query_selector_all("a[href*='/dp/'], a[href*='/gp/slredirect/']")
            print(f"[INFO] Links candidatos encontrados: {len(links)}")
            
            found_count = 0
            for link_el in links:
                try:
                    # Se achamos um link que tem cara de produto, tentamos ver se ele tem desconto perto
                    parent = link_el.query_selector_xpath("..") # Sobe um nível no HTML
                    text_content = parent.inner_text() if parent else ""
                    
                    if "%" in text_content or "off" in text_content.lower():
                        title = link_el.inner_text().strip() or "Produto em Oferta"
                        link = link_el.get_attribute("href").split("?")[0]
                        full_link = link if link.startswith("http") else f"https://www.amazon.com.br{link}"
                        
                        # Se o título for muito curto, ignoramos (evita pegar 'Ver Detalhes')
                        if len(title) < 5: continue
                        
                        prod = {"title": title[:70], "discount": "Ver no site", "link": full_link, "price": "Em promoção"}
                        print(f"[SUCCESS] Detectado: {title[:40]}")
                        send_count += 1
                        if found_count <= 5: # Limite para não inundar o Discord no teste
                            send_to_discord(prod)
                            found_count += 1
                except: continue
                
            if found_count == 0:
                print("[!] Ainda sem itens. Capturando estado final para análise...")
                page.screenshot(path="failed_state.png")

        except Exception as e:
            print(f"[ERRO FATAL] {e}")
        
        browser.close()
        print(f"[FINISHED] Processo finalizado. Itens enviados: {found_count}")

if __name__ == "__main__":
    run()
