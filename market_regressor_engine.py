# -*- coding: utf-8 -*-
import os
import re
import subprocess
import sys
import requests

# --- [BOOTSTRAP] ---
try:
    import pkg_resources
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "setuptools<70.0.0"])
    import pkg_resources
# -------------------

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
                {"name": "Preço Atual", "value": f"**{data_point['preco']}**", "inline": True},
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
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        page = context.new_page()
        stealth_sync(page)

        print(f"[POLLING] Acessando {SAMPLING_SOURCE_URI}...")
        
        try:
            page.goto(SAMPLING_SOURCE_URI, wait_until="load", timeout=60000)
            # Espera um pouco mais para o JavaScript da Amazon renderizar as ofertas
            page.wait_for_timeout(5000)
            page.evaluate("window.scrollTo(0, 1000)")
            page.wait_for_timeout(2000)
        except Exception as e:
            print(f"[WARN] Erro ao carregar página: {e}")

        # SELETORES ATUALIZADOS: Mais abrangentes
        # Procura por cards de oferta usando múltiplos padrões conhecidos
        items = page.query_selector_all("[data-testid='deal-card'], [class*='DealCard'], .a-section.octopus-dlp-asin-section")
        print(f"[INFO] {len(items)} potenciais itens encontrados.")

        for item in items:
            try:
                # Busca título em várias tags possíveis
                titulo_el = item.query_selector("[class*='DealTitle'], [class*='title'], h2, span.a-size-base")
                link_el = item.query_selector("a")
                img_el = item.query_selector("img")
                
                # Busca desconto (procura o símbolo %)
                desconto_el = item.query_selector("span:has-text('%'), [class*='badge-percent-off']")
                
                # Busca preço
                preco_el = item.query_selector(".a-price-whole, [class*='price']")

                if titulo_el and link_el and preco_el:
                    titulo = titulo_el.inner_text().strip()
                    url_raw = link_el.get_attribute("href")
                    if not url_raw: continue
                    
                    url = "https://www.amazon.com.br" + url_raw.split("?")[0] if url_raw.startswith("/") else url_raw.split("?")[0]
                    
                    # Extração de ASIN
                    asin_match = re.search(r'/([A-Z0-9]{10})(?:[/?]|$)', url)
                    item_id = asin_match.group(1) if asin_match else url
                    
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
        print("[INFO] Nenhum item capturado. Tentando seletor de emergência...")
        # Se falhar, pode ser que a Amazon mudou para o layout de lista simples
        return

    # Remove duplicados e ordena
    data_points.sort(key=lambda x: x['desconto'], reverse=True)
    processed_hashes = load_processed_hashes()
    
    posted_count = 0
    for selected in data_points:
        if selected["id"] not in processed_hashes:
            print(f"[OPTIMAL] Enviando: {selected['titulo'][:50]}... (-{selected['desconto']}%)")
            if ingest_to_primary_endpoint(selected):
                persist_data_hash(selected["id"])
                posted_count += 1
                # Limita a 1 post por execução para evitar spam e shadowban do webhook
                break 
    
    if posted_count == 0:
        print("[DEDUP] Nada novo para postar.")

if __name__ == "__main__":
    main()
