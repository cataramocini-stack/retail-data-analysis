# -*- coding: utf-8 -*-
"""
Market Regressor Engine — Stochastic Price Volatility Analyzer
Performs multi-dimensional regression analysis on retail pricing data
sourced from publicly available e-commerce indices (BR market segment).
"""

import os
import re
import subprocess
import sys
import requests

# --- [BOOTSTRAP] SOLUÇÃO PARA O ERRO DE PKG_RESOURCES ---
# Esta secção força a instalação do setuptools se o módulo pkg_resources não for encontrado
try:
    import pkg_resources
except ImportError:
    print("[BOOTSTRAP] Módulo pkg_resources ausente. A instalar dependências legadas...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "setuptools<70.0.0"])
    import pkg_resources
# -------------------------------------------------------

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync

# Bootstrap runtime configuration from local environment manifest
load_dotenv()

# Primary data ingestion and affiliation metric parameters
INGESTION_ENDPOINT_PRIMARY = os.getenv("INGESTION_ENDPOINT_PRIMARY")
AFFILIATION_DATA_METRIC = os.getenv("AFFILIATION_DATA_METRIC")

# Persistent metadata store for processed data hashes
METADATA_STORE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "processed_metadata.db")

# Source URI for stochastic price sampling
SAMPLING_SOURCE_URI = "https://www.amazon.com.br/ofertas"

# Minimum variance threshold for data relevance (percentage)
VARIANCE_THRESHOLD = 20

def load_processed_hashes():
    """Deserializes previously ingested data hashes from persistent store."""
    if not os.path.exists(METADATA_STORE):
        return set()
    with open(METADATA_STORE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())

def persist_data_hash(data_hash):
    """Serializes a new data hash to the persistent metadata store."""
    with open(METADATA_STORE, "a", encoding="utf-8") as f:
        f.write(f"{data_hash}\n")

def ingest_to_primary_endpoint(data_point):
    """Transmits normalized data packet to the configured ingestion endpoint."""
    if not INGESTION_ENDPOINT_PRIMARY:
        print("[ERROR] Primary ingestion endpoint not configured.")
        return False

    # Injeta a métrica de afiliação na URL final
    url_afiliado = data_point['url']
    if AFFILIATION_DATA_METRIC:
        connector = "&" if "?" in url_afiliado else "?"
        url_afiliado = f"{url_afiliado}{connector}tag={AFFILIATION_DATA_METRIC}"

    payload = {
        "embeds": [{
            "title": f"🔥 {data_point['titulo'][:250]}",
            "url": url_afiliado,
            "color": 0xFF9900,
            "fields": [
                {"name": "Preço Original", "value": f"~~{data_point['preco_antigo']}~~", "inline": True},
                {"name": "Preço Atual", "value": f"**{data_point['preco']}**", "inline": True},
                {"name": "Desconto", "value": f"**{data_point['desconto']}%**", "inline": True}
            ],
            "image": {"url": data_point['imagem']},
            "footer": {"text": "Market Regressor — Análise de Volatilidade de Preços"}
        }]
    }

    try:
        response = requests.post(INGESTION_ENDPOINT_PRIMARY, json=payload, timeout=15)
        return response.status_code < 400
    except Exception as e:
        print(f"[ERROR] Ingestion failed: {e}")
        return False

def run_stochastic_polling():
    """Executes the main headless browser sequence for data collection."""
    data_points = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        stealth_sync(page) # Aplica o disfarce de automação

        print(f"[POLLING] Accessing {SAMPLING_SOURCE_URI}...")
        page.goto(SAMPLING_SOURCE_URI, wait_until="networkidle", timeout=60000)
        
        # Scroll para carregar elementos dinâmicos
        page.evaluate("window.scrollTo(0, document.body.scrollHeight/2)")
        page.wait_for_timeout(3000)

        # Seletores de extração (podem precisar de ajuste se a Amazon mudar o layout)
        items = page.query_selector_all("[data-testid='grid-deals-container'] [data-testid='deal-card']")
        
        for item in items:
            try:
                titulo_el = item.query_selector(".//div[contains(@class, 'DealTitle')]")
                link_el = item.query_selector("a")
                precos = item.query_selector_all(".//span[contains(@class, 'a-price')]")
                img_el = item.query_selector("img")

                if titulo_el and link_el and len(precos) >= 1:
                    titulo = titulo_el.inner_text().strip()
                    url = "https://www.amazon.com.br" + link_el.get_attribute("href").split("?")[0]
                    
                    # Extrai ID do produto (ASIN) para o banco de dados
                    asin_match = re.search(r'/(?:dp|gp/product)/([A-Z0-9]{10})', url)
                    item_id = asin_match.group(1) if asin_match else url
                    
                    preco_atual = precos[0].inner_text().replace('\n', ',').strip()
                    preco_antigo = ""
                    desconto = 0

                    # Tenta calcular a variância (desconto)
                    desconto_el = item.query_selector(".//span[contains(@class, 'badge-percent-off')]")
                    if desconto_el:
                        desconto_raw = re.findall(r'\d+', desconto_el.inner_text())
                        desconto = int(desconto_raw[0]) if desconto_raw else 0

                    if desconto >= VARIANCE_THRESHOLD:
                        data_points.append({
                            "id": item_id,
                            "titulo": titulo,
                            "url": url,
                            "preco": preco_atual,
                            "preco_antigo": preco_antigo,
                            "desconto": desconto,
                            "imagem": img_el.get_attribute("src") if img_el else ""
                        })
            except Exception as e:
                continue

        browser.close()
    return data_points

def main():
    print("=" * 60)
    print("[START] Market Regressor Engine Pipeline")
    print("=" * 60)

    data_points = run_stochastic_polling()
    
    if not data_points:
        print("[INFO] No data points meeting variance threshold were identified.")
        return

    # Ordena por maior variância (desconto)
    data_points.sort(key=lambda x: x['desconto'], reverse=True)
    
    processed_hashes = load_processed_hashes()
    selected_point = None

    for dp in data_points:
        if dp["id"] not in processed_hashes:
            selected_point = dp
            break

    if not selected_point:
        print("[DEDUP] All identified data points have already been processed.")
        return

    print(f"[OPTIMAL] Selected: {selected_point['titulo'][:60]}... ({selected_point['desconto']}% off)")

    if ingest_to_primary_endpoint(selected_point):
        persist_data_hash(selected_point["id"])
        print("[SUCCESS] Data packet transmitted and hash persisted.")
    else:
        print("[FAILURE] Transmission failed.")

if __name__ == "__main__":
    main()
