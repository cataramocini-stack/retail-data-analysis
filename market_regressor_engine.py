# -*- coding: utf-8 -*-
import os
import re
import subprocess
import sys
import requests

# --- [BOOTSTRAP SYSTEM] ---
# Resolve o erro de pkg_resources de forma definitiva
try:
    import pkg_resources
except ImportError:
    print("[SYSTEM] Reconfigurando dependências legadas...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "setuptools<70.0.0"])
    import pkg_resources
# --------------------------

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync

load_dotenv()

# Configurações de Ambiente
INGESTION_ENDPOINT_PRIMARY = os.getenv("INGESTION_ENDPOINT_PRIMARY")
AFFILIATION_DATA_METRIC = os.getenv("AFFILIATION_DATA_METRIC")
METADATA_STORE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "processed_metadata.db")
SAMPLING_SOURCE_URI = "https://www.amazon.com.br/ofertas"
VARIANCE_THRESHOLD = 20 # Mínimo de 20% de desconto

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
                {"name": "Desconto", "value": f"**{data_point['desconto']}% OFF**", "inline": True},
                {"name": "Link", "value": "[Ir para Amazon](" + url_afiliado + ")", "inline": True}
            ],
            "image": {"url": data_point['imagem']},
            "footer": {"text": "Market Regressor — Monitoramento em Tempo Real"}
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
        # User agent de Chrome real para evitar bloqueios
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 800}
        )
        page = context.new_page()
        stealth_sync(page)

        print(f"[POLLING] Iniciando captura em: {SAMPLING_SOURCE_URI}")
        
        try:
            # Carregamento rápido
            page.goto(SAMPLING_SOURCE_URI, wait_until="commit", timeout=60000)
            # Simulação de scroll humano para carregar os produtos "escondidos" (lazy load)
            for _ in range(3):
                page.mouse.wheel(0, 800)
                page.wait_for_timeout(1500)
        except Exception as e:
            print(f"[WARN] Navegação interrompida, processando dados parciais...")

        # ESTRATÉGIA: Busca por padrão de link de produto (/dp/...)
        links = page.query_selector_all("a[href*='/dp/'], a[href*='/gp/product/']")
        print(f"[INFO] {len(links)} links candidatos identificados.")

        seen_ids = set()

        for link in links:
            try:
                url_raw = link.get_attribute("href")
                if not url_raw or "javascript" in url_raw: continue
                
                # Normaliza URL e extrai o ID único (ASIN)
                asin_match = re.search(r'/([A-Z0-9]{10})(?:[/?]|$)', url_raw)
                if not asin_match: continue
                item_id = asin_match.group(1)
                
                if item_id in seen_ids: continue
                seen_ids.add(item_id)

                url = f"https://www.amazon.com.br/dp/{item_id}"

                # Analisa o texto ao redor do link para achar o desconto
                # Subimos para o container pai para ler as informações próximas
                container = page.evaluate_handle("el => el.closest('div').parentElement", link)
                bloco_texto = container.evaluate("el => el.innerText")

                # Procura por números seguidos de % (ex: 30%)
                percent_match = re.search(r'(\d+)%', bloco_texto)
                desconto = int(percent_match.group(1)) if percent_match else 0

                if desconto >= VARIANCE_THRESHOLD:
                    # Busca imagem próxima ao link
                    img_el = container.query_selector("img")
                    img_url = img_el.get_attribute("src") if img_el else ""
                    
                    # Título da oferta
                    titulo = link.inner_text().strip()
                    if len(titulo) < 10: # Se o link for curto (ex: imagem), tenta o texto do container
                        titulo = bloco_texto.split('\n')[0][:100]

                    data_points.append({
                        "id": item_id,
                        "titulo": titulo,
                        "url": url,
                        "desconto": desconto,
                        "imagem": img_url
                    })
            except: continue
            
        browser.close()
    return data_points

def main():
    print("=" * 60)
    print("[START] Market Regressor Engine — Pipeline Ativo")
    print("=" * 60)
    
    data_points = run_stochastic_polling()
    
    if not data_points:
        print("[INFO] Nenhuma nova oferta detectada nesta rodada.")
        return

    # Ordena: maior desconto primeiro
    data_points.sort(key=lambda x: x['desconto'], reverse=True)
    processed_hashes = load_processed_hashes()
    
    for item in data_points:
        if item["id"] not in processed_hashes:
            print(f"[MATCH] Postando: {item['id']} com {item['desconto']}% OFF")
            if ingest_to_primary_endpoint(item):
                persist_data_hash(item["id"])
                print("[SUCCESS] Webhook disparado com sucesso.")
                break # Envia um por vez para evitar bloqueio
    else:
        print("[DEDUP] Todas as ofertas encontradas já foram processadas.")

if __name__ == "__main__":
    main()
