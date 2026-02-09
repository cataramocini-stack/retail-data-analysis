import os
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
import requests

load_dotenv()
DISCORD_WEBHOOK = os.getenv("INGESTION_ENDPOINT_PRIMARY")

def send_to_discord(product):
    payload = {"content": f"🔥 **TESTE DE CONEXÃO!**\n📦 **{product['title']}**\n🔗 {product['link']}"}
    requests.post(DISCORD_WEBHOOK, json=payload)

def run():
    print("="*60)
    print("[START] Teste de Força Bruta")
    print("="*60)
    with sync_playwright() as p:
        # Lançamos o navegador com flags de 'humano'
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
        
        # Simulamos um Windows real com resolução comum
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 720}
        )
        page = context.new_page()
        
        print("[POLLING] Tentando acessar o Google para testar internet...")
        try:
            # Teste 1: O robô consegue ver o Google?
            page.goto("https://www.google.com", timeout=30000)
            print(f"[OK] Internet está funcionando. Título: {page.title()}")
            
            # Teste 2: Mercado Livre simplificado
            print("[POLLING] Tentando Mercado Livre...")
            page.goto("https://www.mercadolivre.com.br", wait_until="domcontentloaded")
            
            # Em vez de esperar seletor, vamos pegar o que tiver de link
            page.wait_for_timeout(5000)
            links = page.query_selector_all("a")
            print(f"[INFO] Links encontrados: {len(links)}")
            
            if len(links) > 0:
                print("[SUCCESS] O robô está conseguindo ler a página!")
                send_to_discord({"title": "Bot Online e Lendo Páginas!", "link": "https://www.mercadolivre.com.br"})
            else:
                print("[FALHA] A página carregou, mas está vazia (bloqueio de script).")
                page.screenshot(path="final_debug.png")

        except Exception as e:
            print(f"[ERRO CRÍTICO] Falha total de navegação: {e}")
        
        browser.close()

if __name__ == "__main__":
    run()
