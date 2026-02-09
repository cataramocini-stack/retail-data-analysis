# -*- coding: utf-8 -*-
import os
import re
import subprocess
import sys
import requests

# --- [BOOTSTRAP] SOLUÇÃO PARA O ERRO DE PKG_RESOURCES ---
try:
    import pkg_resources
except ImportError:
    print("[BOOTSTRAP] Módulo pkg_resources ausente. Instalando dependências legadas...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "setuptools<70.0.0"])
    import pkg_resources
# -------------------------------------------------------

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

    payload = {
        "embeds": [{
            "title": f"🔥 {data_point['titulo'][:250]}",
            "url": url_afiliado,
            "color": 0xFF9900,
            "fields": [
                {"name": "Preço", "value": f"**{data_point['preco']}**", "inline": True},
                {"name": "Desconto", "value": f"**{data_point['desconto']}%**", "inline": True}
            ],
            "image": {"url": data_point['imagem']},
            "footer": {"text": "Market Regressor — Oferta Detectada"}
        }]
    }
    try:
        response = requests.post(INGESTION_ENDPOINT_PRIMARY, json=payload, timeout=15)
        return response.status_code < 400
    except: return False

def run_stochastic_polling():
    data_points = []
    with sync_playwright() as p:
        # Lançamos o browser com argumentos extras para evitar detecção
        browser = p.chromium.launch(headless=True, args=['--disable-http2'])
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()
        stealth_sync(page)

        print(f"[POLLING] Acessando {SAMPLING_SOURCE_URI}...")
        
        # MUDANÇA AQUI: Esperamos apenas o DOM carregar, não a rede inteira
        try:
            page.goto(SAMPLING_SOURCE_URI, wait_until="domcontentloaded", timeout=45000)
            # Espera manual curta para os itens aparecerem
            page.wait_for_selector("[data-testid='deal-card']", timeout=15000)
        except Exception as e:
            print(f"[WARN] Timeout parcial, tentando processar o que foi carregado...")

        # Scroll suave para ativar o carregamento das imagens
        page.evaluate("window.scrollBy(0, 800)")
        page.wait_for_timeout(2000)

        items = page.query_selector_all("[data-testid='deal-card']")
        print(f"[INFO] {len(items)} itens encontrados na vitrine.")

        for item in items:
            try:
                titulo_el = item.query_selector("[data-testid='deal-title'], .DealTitle-module__truncate_s9966")
                link_el = item.query_selector("a")
                img_el = item.query_selector("img")
                
                # Preço e Desconto
                preco_el = item.query_selector(".a-price-whole")
                desconto_el = item.query_selector("[class*='badge-percent-off']")

                if titulo_el and link_el and preco_el:
                    titulo = titulo_el.inner_text().strip()
                    url = "https://www.amazon.com.br" + link_el.get_attribute("href").split("?")[0]
                    
                    asin_match = re.search(r'/([A-Z0-9]{10})(?:[/?]|$)', url)
                    item_id = asin_match.group(1) if asin_match else url
                    
                    # Limpeza do desconto
                    desconto = 0
                    if desconto_el:
                        d_text = re.findall(r'\d+', desconto_el.inner_text())
                        desconto = int(d_text[0]) if d_text else 0

                    if desconto >= VARIANCE_THRESHOLD:
                        data_points.append({
                            "id": item_id,
                            "titulo": titulo,
                            "url": url,
                            "preco": f"R$ {preco_el.inner_text().strip()}",
                            "desconto": desconto,
                            "imagem": img_el.get_attribute("src") if img_el else ""
                        })
            except: continue
        browser.close()
    return data_points

def main():
    print("=" * 60)
    print("[START] Market Regressor Engine")
    print("=" * 60)
    
    data_points = run_stochastic_polling()
    if not data_points:
        print("[INFO] Nenhuma oferta acima do threshold encontrada agora.")
        return

    data_points.sort(key=lambda x: x['desconto'], reverse=True)
    processed_hashes = load_processed_hashes()
    
    for selected in data_points:
        if selected["id"] not in processed_hashes:
            print(f"[OPTIMAL] Postando: {selected['titulo'][:50]}... (-{selected['desconto']}%)")
            if ingest_to_primary_endpoint(selected):
                persist_data_hash(selected["id"])
                print("[SUCCESS] Webhook enviado.")
                return
    
    print("[DEDUP] Todas as ofertas encontradas já foram postadas anteriormente.")

if __name__ == "__main__":
    main()
