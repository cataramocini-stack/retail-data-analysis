# -*- coding: utf-8 -*-
import os, re, requests
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

def run():
    print("=" * 60)
    print("[START] Market Regressor — Versão Final Ultra Precision")
    print("=" * 60)
    
    processed_ids = load_processed_ids()
    round_ids = set()
    found_count = 0
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        context = browser.new_context(user_agent=ua, viewport={'width': 1280, 'height': 720})
        page = context.new_page()
        
        try:
            print("[POLLING] Acessando Amazon...")
            page.goto("https://www.amazon.com.br/ofertas", wait_until="load", timeout=60000)
            page.wait_for_timeout(5000)
            
            cards = page.query_selector_all("[data-testid='grid-desktop-item']")
            if not cards: cards = page.query_selector_all("div:has(a[href*='/dp/'])")
                
            print(f"[INFO] Elementos detectados: {len(cards)}")
            
            for card in cards:
                try:
                    # 1. ASIN
                    link_el = card.query_selector("a[href*='/dp/']")
                    if not link_el: continue
                    asin = re.search(r'/([A-Z0-9]{10})', link_el.get_attribute("href")).group(1)
                    if asin in processed_ids or asin in round_ids: continue

                    # 2. TÍTULO (ALT da imagem)
                    img = card.query_selector("img")
                    titulo = img.get_attribute("alt") if img else ""
                    if len(titulo) < 15 or "volta às aulas" in titulo.lower(): continue

                    # 3. TEXTO E DESCONTO
                    card_text = card.inner_text()
                    d_match = re.search(r'(\d+)%', card_text)
                    if not d_match: continue
                    desconto_site = int(d_match.group(1))

                    # 4. PREÇOS COM VALIDAÇÃO MATEMÁTICA
                    # Busca preços no formato R$ XX,XX
                    precos_raw = re.findall(r'R\$\s?([\d\.]+,[\d]{2})', card_text)
                    vals = []
                    for p_raw in precos_raw:
                        try:
                            num = float(p_raw.replace('.', '').replace(',', '.').strip())
                            if num > 5: vals.append((num, f"R$ {p_raw}"))
                        except: continue
                    
                    if len(vals) < 1: continue
                    vals.sort() # Menor primeiro
                    
                    p_por_val, p_por_str = vals[0]
                    p_de_val, p_de_str = vals[-1] if len(vals) > 1 else (0, "---")

                    # VALIDAÇÃO DE SEGURANÇA:
                    # Se o preço "DE" for absurdamente maior que o "POR" (ex: 9000 vs 170)
                    # e o desconto não condiz com essa diferença, usamos apenas o preço "POR"
                    if p_de_val > 0:
                        desc_real = 100 - (p_por_val / p_de_val * 100)
                        # Se a diferença entre o desconto do site e o real for maior que 15%
                        if abs(desc_real - desconto_site) > 15:
                            p_de_str = "---" 

                    # 5. POSTAGEM
                    msg = (f"📦 **OFERTA - {titulo[:95]} - "
                           f"DE {p_de_str} por {p_por_str} ({desconto_site}% OFF) 🔥**\n"
                           f"https://www.amazon.com.br/dp/{asin}?tag={AFFILIATE_TAG}")
                    
                    res = requests.post(DISCORD_WEBHOOK, json={"content": msg}, timeout=15)
                    if res.status_code < 400:
                        save_id(asin)
                        round_ids.add(asin)
                        print(f"[SUCCESS] {titulo[:30]}")
                        found_count += 1
                        if found_count >= 5: break
                except: continue
                
        except Exception as e: print(f"[ERRO] {e}")
        finally:
            browser.close()
            print(f"[FINISHED] Enviados: {found_count}")

if __name__ == "__main__":
    run()
