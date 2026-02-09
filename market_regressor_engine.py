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

    # FORMATO ATUALIZADO: 📦 **OFERTA - Nome do Produto - DE R$X por R$Y (Z% OFF) 🔥**
    frase = (
        f"📦 **OFERTA - {data_point['titulo']} - "
        f"DE {data_point['preco_de']} por {data_point['preco_por']} "
        f"({data_point['desconto']}% OFF) 🔥**"
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
            page.goto(SAMPLING_SOURCE_URI, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(5000)
            for _ in range(4):
                page.mouse.wheel(0, 1000)
                page.wait_for_timeout(1000)
        except: pass

        # Seleciona os cards de oferta
        cards = page.query_selector_all("div:has(a[href*='/dp/'])")
        seen_ids = set()

        for card in cards:
            try:
                link_el = card.query_selector("a[href*='/dp/']")
                if not link_el: continue
                
                url_raw = link_el.get_attribute("href")
                asin_match = re.search(r'/([A-Z0-9]{10})(?:[/?]|$)', url_raw)
                if not asin_match: continue
                asin = asin_match.group(1)
                
                if asin in seen_ids: continue
                seen_ids.add(asin)

                texto_total = card.inner_text()
                linhas = [l.strip() for l in texto_total.split('\n') if len(l.strip()) > 1]

                # --- LÓGICA DE TÍTULO ROBUSTA ---
                # Se o link_el.inner_text vier com "45% OFF", nós ignoramos e buscamos o nome real
                titulo_candidato = link_el.inner_text().strip()
                
                if not titulo_candidato or "%" in titulo_candidato or "R$" in titulo_candidato:
                    # Se o título do link for inválido, pegamos a linha mais longa do card (geralmente é o nome)
                    # Filtramos linhas que contém preços ou porcentagens
                    candidatos = [l for l in linhas if "%" not in l and "R$" not in l and "Oferta" not in l]
                    titulo = candidatos[0] if candidatos else "Produto em Oferta"
                else:
                    titulo = titulo_candidato

                # --- PREÇOS E DESCONTO ---
                precos_encontrados = re.findall(r'R\$\s?\d+[.,]\d{2}', texto_total)
                if not precos_encontrados: continue

                precos_numericos = []
                for p_str in precos_encontrados:
                    n = float(p_str.replace('R$', '').replace('.', '').replace(',', '.').strip())
                    precos_numericos.append((n, p_str))
                
                precos_numericos.sort()
                preco_por = precos_numericos[0][1]
                preco_de = precos_numericos[-1][1] if len(precos_numericos) > 1 else "---"

                desc_match = re.search(r'(\d+)%', texto_total)
                desconto = int(desc_match.group(1)) if desc_match else 0
                
                if desconto < VARIANCE_THRESHOLD: continue

                data_points.append({
                    "id": asin,
                    "titulo": titulo[:80].strip(), # Corta para não ficar gigante
                    "url": f"https://www.amazon.com.br/dp/{asin}",
                    "preco_de": preco_de,
                    "preco_por": preco_por,
                    "desconto": desconto
                })
            except: continue
            
        browser.close()
    return data_points

def main():
    print("=" * 60)
    print("[START] Market Regressor — Final Style Mode")
    print("=" * 60)
    
    data_points = run_stochastic_polling()
    if not data_points: return

    data_points.sort(key=lambda x: x['desconto'], reverse=True)
    processed_hashes = load_processed_hashes()
    
    for item in data_points:
        if item["id"] not in processed_hashes:
            if ingest_to_primary_endpoint(item):
                persist_data_hash(item["id"])
                print(f"[SUCCESS] Postado: {item['titulo']}")
                break 

if __name__ == "__main__":
    main()
