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

    # O FORMATO QUE VOCÊ GOSTA: TUDO EM UMA LINHA
    # OFERTA - nome - DE (R$ X) por (R$ Y) (Z% OFF) 🔥
    frase = (
        f"OFERTA - {data_point['titulo']} - "
        f"DE {data_point['preco_de']} por {data_point['preco_por']} "
        f"({data_point['desconto']}% OFF) 🔥"
    )

    payload = {"content": f"{frase}\n{url_afiliado}"}
    
    try:
        response = requests.post(INGESTION_ENDPOINT_PRIMARY, json=payload, timeout=15)
        return response.status_code < 400
    except: return False

def run_stochastic_polling():
    data_points = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        stealth_sync(page)

        print(f"[POLLING] Capturando em: {SAMPLING_SOURCE_URI}")
        
        try:
            # Vamos esperar o carregamento completo e dar um tempo para os scripts da Amazon rodarem
            page.goto(SAMPLING_SOURCE_URI, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(5000)
            
            # Scroll mais "pesado" para carregar as ofertas
            for _ in range(4):
                page.mouse.wheel(0, 1000)
                page.wait_for_timeout(1000)
        except: 
            print("[WARN] Tempo de espera excedido, tentando processar o que carregou.")

        # Buscamos por qualquer container que tenha cara de produto e contenha um link
        # Essa busca é mais genérica para não quebrar se a Amazon mudar as classes
        cards = page.query_selector_all("div:has(a[href*='/dp/'])")
        
        seen_ids = set()
        print(f"[DEBUG] {len(cards)} blocos suspeitos encontrados.")

        for card in cards:
            try:
                # Extrair o link primeiro
                link_el = card.query_selector("a[href*='/dp/']")
                if not link_el: continue
                
                url_raw = link_el.get_attribute("href")
                asin_match = re.search(r'/([A-Z0-9]{10})(?:[/?]|$)', url_raw)
                if not asin_match: continue
                asin = asin_match.group(1)
                
                if asin in seen_ids: continue
                seen_ids.add(asin)

                # Captura o texto total do bloco de oferta
                texto_total = card.inner_text()
                
                # Se não tem o símbolo de %, provavelmente não é uma oferta com desconto visível
                if "%" not in texto_total: continue

                # Mineração de Preços (R$ 0,00)
                # O regex pega o padrão brasileiro de moeda
                precos_encontrados = re.findall(r'R\$\s?\d+[.,]\d{2}', texto_total)
                if len(precos_encontrados) < 1: continue

                # Lógica de Preços:
                # Se tiver 2 preços, o maior é o "DE" e o menor é o "POR"
                # Se tiver apenas 1, usamos ele como "POR" e deixamos o "DE" genérico
                precos_numericos = []
                for p_str in precos_encontrados:
                    n = float(p_str.replace('R$', '').replace('.', '').replace(',', '.').strip())
                    precos_numericos.append((n, p_str))
                
                precos_numericos.sort() # Menor primeiro
                
                preco_por = precos_numericos[0][1]
                preco_de = precos_numericos[-1][1] if len(precos_numericos) > 1 else "---"

                # Extração do Desconto
                desc_match = re.search(r'(\d+)%', texto_total)
                desconto = int(desc_match.group(1)) if desc_match else 0
                
                if desconto < VARIANCE_THRESHOLD: continue

                # Título (limpeza radical)
                titulo_sujo = link_el.inner_text().strip() or texto_total.split('\n')[0]
                titulo = titulo_sujo.replace('\n', ' ').strip()[:70]

                data_points.append({
                    "id": asin,
                    "titulo": titulo,
                    "url": f"https://www.amazon.com.br/dp/{asin}",
                    "preco_de": preco_de,
                    "preco_por": preco_por,
                    "desconto": desconto
                })
            except:
                continue
            
        browser.close()
    return data_points

def main():
    print("=" * 60)
    print("[START] Market Regressor — Visual One-Line Mode")
    print("=" * 60)
    
    data_points = run_stochastic_polling()
    
    # Se não achar nada no modo normal, o bot avisará aqui
    if not data_points:
        print("[INFO] Zero ofertas detectadas. Verificando bloqueio ou mudança de layout.")
        return

    print(f"[INFO] {len(data_points)} ofertas encontradas.")
    data_points.sort(key=lambda x: x['desconto'], reverse=True)
    
    processed_hashes = load_processed_hashes()
    
    for item in data_points:
        if item["id"] not in processed_hashes:
            print(f"[MATCH] Tentando postar: {item['titulo']}")
            if ingest_to_primary_endpoint(item):
                persist_data_hash(item["id"])
                print("[SUCCESS] Postado no Discord com sucesso!")
                return 
    
    print("[DEDUP] Tudo o que foi encontrado já tinha sido postado.")

if __name__ == "__main__":
    main()
