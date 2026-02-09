# -*- coding: utf-8 -*-
import os, re, requests, random
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
    print("[START] Market Regressor — Versão Estável 1 Post")
    print("=" * 60)
    
    processed_ids = load_processed_ids()
    round_ids = set()
    found_count = 0
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        ]
        context = browser.new_context(user_agent=random.choice(user_agents), viewport={'width': 1280, 'height': 3000})
        page = context.new_page()
        
        try:
            print("[POLLING] Acessando Amazon...")
            page.goto("https://www.amazon.com.br/ofertas", wait_until="load", timeout=60000)
            
            print("[SCROLLING] Carregando mais ofertas...")
            for _ in range(5):
                page.mouse.wheel(0, 1500)
                page.wait_for_timeout(2000)
            
            # Tenta múltiplos seletores comuns da Amazon
            cards = page.query_selector_all("[data-testid='grid-desktop-item']")
            if not cards:
                cards = page.query_selector_all("div[id*='grid-desktop-item']")
            if not cards:
                cards = page.query_selector_all(".a-section.oct-desktop-grid-item")
                
            print(f"[INFO] Elementos detectados: {len(cards)}")
            
            for card in cards:
                try:
                    link_el = card.query_selector("a[href*='/dp/']")
                    if not link_el: continue
                    
                    asin_match = re.search(r'/([A-Z0-9]{10})', link_el.get_attribute("href"))
                    if not asin_match: continue
                    asin = asin_match.group(1)

                    if asin in processed_ids or asin in round_ids: continue

                    img = card.query_selector("img")
                    titulo = img.get_attribute("alt") if img else ""
                    if len(titulo) < 10: continue

                    card_text = card.inner_text()
                    precos = re.findall(r'R\$\s?([\d\.]+,[\d]{2})', card_text)
                    if not precos: continue
                    
                    # Pegamos o menor preço como "Por" e o maior como "De"
                    precos_float = sorted([float(p.replace('.','').replace(',','.')) for p in precos])
                    p_por = f"R$ {precos[0]}" 

                    msg = (f"📦 **OFERTA DETECTADA - {titulo[:90]}**\n\n"
                           f"💰 **Por apenas {p_por} 🔥**\n"
                           f"🛒 Link: https://www.amazon.com.br/dp/{asin}?tag={AFFILIATE_TAG}")
                    
                    res = requests.post(DISCORD_WEBHOOK, json={"content": msg}, timeout=15)
                    if res.status_code < 400:
                        save_id(asin)
                        round_ids.add(asin)
                        print(f"[SUCCESS] Enviado: {asin}")
                        found_count += 1
                        if found_count >= 1: break
                except:
                    continue
                    
        except Exception as e:
            print(f"[ERRO] {e}")
        finally:
            browser.close()
            print(f"[FINISHED] Enviados: {found_count}")

if __name__ == "__main__":
    run()
