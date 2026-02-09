# -*- coding: utf-8 -*-
import os
import re
import subprocess
import sys
import requests

# --- [BOOTSTRAP SYSTEM] ---
try:
    import pkg_resources
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "setuptools<70.0.0"])
    import pkg_resources
# --------------------------

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync

load_dotenv()

INGESTION_ENDPOINT_PRIMARY = os.getenv("INGESTION_ENDPOINT_PRIMARY")
AFFILIATION_DATA_METRIC = os.getenv("AFFILIATION_DATA_METRIC")
METADATA_STORE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "processed_metadata.db")
SAMPLING_SOURCE_URI = "https://www.amazon.com.br/ofertas"
VARIANCE_THRESHOLD = 20

def load_processed_hashes():
    if not os.path.exists(METADATA_STORE): return set()
    with open(METADATA_STORE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())

def persist_data_hash(data_hash):
    with open(METADATA_STORE, "a", encoding="utf-8") as f:
        f.write(f"{data_hash}\n")

def ingest_to_primary_endpoint(data_point):
    if not INGESTION_ENDPOINT_PRIMARY: return False
    url_afiliado = data_point['url']
    if AFFILIATION_DATA_METRIC:
        connector = "&" if "?" in url_afiliado else "?"
        url_afiliado = f"{url_afiliado}{connector}tag={AFFILIATION_DATA_METRIC}"

    # MONTAGEM DA FRASE ESTILO "OFERTA" (TUDO EM UMA LINHA)
    # Formato: OFERTA - Nome - DE R$X por R$Y (Z% OFF) 🔥
    titulo_formatado = (
        f"OFERTA - {data_point['titulo'][:80]} - "
        f"DE {data_point['preco_antigo']} por {data_point['preco_atual']} "
        f"({data_point['desconto']}% OFF) 🔥"
    )

    payload = {
        "content": f"{titulo_formatado}\n{url_afiliado}"
    }
    
    try:
        response = requests.post(INGESTION_ENDPOINT_PRIMARY, json=payload, timeout=15)
        return response.status_code < 400
    except: return False

def run_stochastic_polling():
    data_points = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        stealth_sync(page)

        print(f"[POLLING] Capturando ofertas em: {SAMPLING_SOURCE_URI}")
        
        try:
            page.goto(SAMPLING_SOURCE_URI, wait_until="load", timeout=60000)
            for _ in range(2): # Scroll para carregar
                page.mouse.wheel(0, 1000)
                page.wait_for_timeout(2000)
        except: pass

        # Busca por todos os blocos de oferta
        items = page.query_selector_all("[data-testid='deal-card'], .a-section.octopus-dlp-asin-section")
        
        for item in items:
            try:
                link_el = item.query_selector("a[href*='/dp/'], a[href*='/gp/product/']")
                if not link_el: continue
                
                url_raw = link_el.get_attribute("href")
                asin_match = re.search(r'/([A-Z0-9]{10})(?:[/?]|$)', url_raw)
                if not asin_match: continue
                item_id = asin_match.group(1)
                
                # Captura de Preços e Título
                texto_bloco = item.inner_text()
                linhas = [l.strip() for l in texto_bloco.split('\n') if l.strip()]
                
                # Busca desconto (ex: 30% ou -30%)
                percent_match = re.search(r'(\d+)%', texto_bloco)
                desconto = int(percent_match.group(1)) if percent_match else 0

                if desconto >= VARIANCE_THRESHOLD:
                    # Título: Geralmente é a linha mais longa ou específica
                    titulo = link_el.inner_text().strip() or linhas[0]
                    
                    # Tenta capturar os valores monetários (Padrão R$ XX,XX)
                    valores = re.findall(r'R\$\s?\d+[\.,]\d{2}', texto_bloco)
                    
                    if len(valores) >= 2:
                        preco_antigo = valores[1] # Geralmente o segundo valor é o riscado/antigo
                        preco_atual = valores[0]  # O primeiro é o preço de oferta
                    elif len(valores) == 1:
                        preco_antigo = "valor original"
                        preco_atual = valores[0]
                    else:
                        continue # Sem preço, sem post

                    data_points.append({
                        "id": item_id,
                        "titulo": titulo,
                        "url": f"https://www.amazon.com.br/dp/{item_id}",
                        "preco_antigo": preco_antigo,
                        "preco_atual": preco_atual,
                        "desconto": desconto
                    })
            except: continue
            
        browser.close()
    return data_points

def main():
    print("=" * 60)
    print("[START] Market Regressor — Visual Mode")
    print("=" * 60)
    
    data_points = run_stochastic_polling()
    if not data_points: return

    data_points.sort(key=lambda x: x['desconto'], reverse=True)
    processed_hashes = load_processed_hashes()
    
    for item in data_points:
        if item["id"] not in processed_hashes:
            if ingest_to_primary_endpoint(item):
                persist_data_hash(item["id"])
                print(f"[SUCCESS] Postado: {item['id']}")
                break 

if __name__ == "__main__":
    main()
