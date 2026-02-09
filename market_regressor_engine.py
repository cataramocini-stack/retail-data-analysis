# -*- coding: utf-8 -*-
import os
import re
import requests
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

load_dotenv()

DISCORD_WEBHOOK = os.getenv("INGESTION_ENDPOINT_PRIMARY")
AFFILIATE_TAG = os.getenv("AFFILIATION_DATA_METRIC", "scriptoriu01a-20")
METADATA_STORE = "processed_metadata.db"

def load_processed_ids():
    if not os.path.exists(METADATA_STORE): return set()
    with open(METADATA_STORE, "r") as f:
        return set(line.strip() for line in f)

def save_id(asin):
    with open(METADATA_STORE, "a") as f:
        f.write(f"{asin}\n")

def send_to_discord(item):
    # Formatação EXATA que você pediu
    frase = (
        f"📦 **OFERTA - {item['titulo']} - "
        f"DE {item['preco_de']} por {item['preco_por']} "
        f"({item['desconto']}% OFF) 🔥**"
    )
    payload = {"content": f"{frase}\n{item['url']}?tag={AFFILIATE_TAG}"}
    try:
        requests.post(DISCORD_WEBHOOK, json=payload, timeout=15)
        return True
    except:
        return False

def run():
    print("=" * 60)
    print("[START] Market Regressor — Ajuste de Precisão")
    print("=" * 60)
    
    processed_ids = load_processed_ids()
    round_ids = set() # Evita repetição na mesma rodada
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36...")
        page = context.new_page()
        
        try:
            page.goto("https://www.amazon.com.br/ofertas", wait_until="load", timeout=90000)
            page.wait_for_timeout(5000)
            page.mouse.wheel(0, 1000)
            page.wait_for_timeout(5000)
            
            cards = page.query_selector_all("[data-testid='grid-desktop-item']")
            print(f"[INFO] Cards detectados: {len(cards)}")
            
            found_count = 0
            for card in cards:
                try:
                    # 1. PEGAR ASIN (ID ÚNICO)
                    link_el = card.query_selector("a[href*='/dp/']")
                    if not link_el: continue
                    url_raw = link_el.get_attribute("href")
                    asin = re.search(r'/([A-Z0-9]{10})', url_raw).group(1)
                    
                    if asin in processed_ids or asin in round_ids: continue

                    # 2. PEGAR DESCONTO
                    desc_el = card.query_selector("[class*='badge-percent-off'], [class*='savingsPercentage']")
                    if not desc_el: continue
                    desconto = int(''.join(filter(str.isdigit, desc_el.inner_text())))
                    if desconto < 10: continue

                    # 3. PEGAR TÍTULO REAL (Busca o elemento de texto do link)
                    title_el = card.query_selector(".a-truncate-cut, h3, .p13n-sc-truncate")
                    titulo = title_el.inner_text().strip() if title_el else "Produto"
                    
                    # Limpeza: Se o título for só marketing, tentamos o 'alt' da imagem
                    if "menor preço" in titulo.lower() or len(titulo) < 15:
                        img = card.query_selector("img")
                        if img: titulo = img.get_attribute("alt")

                    # 4. PREÇOS (Lógica melhorada)
                    texto_card = card.inner_text()
                    precos = re.findall(r'R\$\s?[\d.,]+', texto_card)
                    
                    # Filtra preços duplicados e limpa
                    limpos = []
                    for p in precos:
                        val = float(p.replace('R$', '').replace('.', '').replace(',', '.').strip())
                        if val not in [v[0] for v in limpos]:
                            limpos.append((val, p))
                    
                    limpos.sort() # Menor preço primeiro
                    if not limpos: continue
                    
                    preco_por = limpos[0][1]
                    preco_de = limpos[-1][1] if len(limpos) > 1 else "---"

                    item_data = {
                        "id": asin,
                        "titulo": titulo[:100],
                        "url": f"https://www.amazon.com.br/dp/{asin}",
                        "preco_de": preco_de,
                        "preco_por": preco_por,
                        "desconto": desconto
                    }

                    if send_to_discord(item_data):
                        save_id(asin)
                        round_ids.add(asin)
                        print(f"[SUCCESS] {titulo[:30]}")
                        found_count += 1
                        if found_count >= 5: break 
                except: continue

        except Exception as e: print(f"[ERRO] {e}")
        finally: browser.close()
        print(f"[FINISHED] Enviados: {found_count}")

if __name__ == "__main__":
    run()
