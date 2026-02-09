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

# Configurações
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

    # MONTAGEM DO TEXTO (EXATAMENTE COMO VOCÊ PEDIU)
    # OFERTA - Nome do produto - DE (Preço Original) por (Preço com Desconto) (% do desconto) 🔥
    frase_oferta = (
        f"OFERTA - {data_point['titulo']} - "
        f"DE {data_point['preco_de']} por {data_point['preco_por']} "
        f"({data_point['desconto']}% OFF) 🔥"
    )

    payload = {
        "content": f"{frase_oferta}\n{url_afiliado}"
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

        print(f"[POLLING] Capturando em: {SAMPLING_SOURCE_URI}")
        
        try:
            page.goto(SAMPLING_SOURCE_URI, wait_until="load", timeout=60000)
            page.wait_for_timeout(3000)
            # Scroll para carregar os produtos dinâmicos
            page.mouse.wheel(0, 1500)
            page.wait_for_timeout(2000)
        except: pass

        # Captura todos os blocos de produtos que tenham links de produto
        cards = page.query_selector_all("div:has(a[href*='/dp/']), div:has(a[href*='/gp/product/'])")
        
        seen_asins = set()

        for card in cards:
            try:
                # 1. Busca o Link e o ASIN (ID do produto)
                link_el = card.query_selector("a[href*='/dp/'], a[href*='/gp/product/']")
                if not link_el: continue
                url_raw = link_el.get_attribute("href")
                asin_match = re.search(r'/([A-Z0-9]{10})(?:[/?]|$)', url_raw)
                if not asin_match: continue
                asin = asin_match.group(1)
                
                if asin in seen_asins: continue
                seen_asins.add(asin)

                # 2. Captura todo o texto do card para minerar preços
                texto_card = card.inner_text()
                
                # 3. Busca Desconto (%)
                desc_match = re.search(r'(\d+)%', texto_card)
                if not desc_match: continue
                desconto = int(desc_match.group(1))
                if desconto < VARIANCE_THRESHOLD: continue

                # 4. Busca Preços (Regex para R$ 0,00)
                precos = re.findall(r'R\$\s?\d+[.,]\d{2}', texto_card)
                if not precos: continue
                
                # Lógica: O menor preço costuma ser o "POR" e o maior o "DE"
                # Limpamos os valores para comparar numericamente
                valores_limpos = []
                for p_str in precos:
                    val = float(p_str.replace('R$', '').replace('.', '').replace(',', '.').strip())
                    valores_limpos.append((val, p_str))
                
                valores_limpos.sort() # Ordena do menor para o maior
                
                preco_por = valores_limpos[0][1] # Menor valor
                preco_de = valores_limpos[-1][1] if len(valores_limpos) > 1 else "Preço Original"

                # 5. Busca Título (melhorado)
                titulo = link_el.inner_text().strip()
                if len(titulo) < 10:
                    # Se o link for vazio (imagem), pega a primeira linha de texto que não seja preço/desconto
                    linhas = [l.strip() for l in texto_card.split('\n') if len(l.strip()) > 10]
                    titulo = linhas[0] if linhas else "Oferta Especial"

                data_points.append({
                    "id": asin,
                    "titulo": titulo[:100],
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
    print("[START] Market Regressor — Estilo de Postagem Clássico")
    print("=" * 60)
    
    data_points = run_stochastic_polling()
    print(f"[INFO] {len(data_points)} ofertas qualificadas encontradas.")

    if not data_points: return

    # Ordena por desconto
    data_points.sort(key=lambda x: x['desconto'], reverse=True)
    processed_hashes = load_processed_hashes()
    
    for item in data_points:
        if item["id"] not in processed_hashes:
            print(f"[MATCH] Postando: {item['id']}")
            if ingest_to_primary_endpoint(item):
                persist_data_hash(item["id"])
                print("[SUCCESS] Post enviado ao Discord.")
                break 

if __name__ == "__main__":
    main()
