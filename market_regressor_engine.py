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
    print("[START] Market Regressor — Versão Final 100% Funcional")
    print("=" * 60)
    
    processed_ids = load_processed_ids()
    round_ids = set()
    found_count = 0
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
        )
        page = context.new_page()
        
        try:
            print("[POLLING] Acessando Amazon...")
            page.goto("https://www.amazon.com.br/ofertas", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)

            print("[SCROLLING] Carregando ofertas...")
            for _ in range(4):
                page.mouse.wheel(0, 1500)
                page.wait_for_timeout(2000)

            # Usa o seletor que funcionou no seu log
            cards = page.query_selector_all("div:has(a[href*='/dp/'])")
            print(f"[INFO] Elementos detectados: {len(cards)}")
            
            for card in cards:
                try:
                    # 1. Link e ASIN
                    link_el = card.query_selector("a[href*='/dp/']")
                    if not link_el: continue
                    href = link_el.get_attribute("href")
                    asin_match = re.search(r'/([A-Z0-9]{10})', href)
                    if not asin_match: continue
                    asin = asin_match.group(1)

                    if asin in processed_ids or asin in round_ids: continue

                    # 2. Título (Pega o Alt da imagem ou o texto do link)
                    img = card.query_selector("img")
                    titulo = img.get_attribute("alt") if img else card.inner_text().split('\n')[0]
                    if len(titulo) < 10: continue

                    # 3. Extração de Preços via Texto (Mais robusto para grades variadas)
                    card_text = card.inner_text()
                    
                    # Captura a porcentagem de desconto anunciada
                    d_match = re.search(r'(\d+)%', card_text)
                    desconto_site = int(d_match.group(1)) if d_match else 0
                    if desconto_site < 5: continue # Filtro mínimo

                    # Captura todos os valores em R$ presentes no card
                    precos_encontrados = re.findall(r'R\$\s?([\d\.]+,[\d]{2})', card_text)
                    if not precos_encontrados: continue

                    # Converte para float e remove duplicatas mantendo a ordem
                    vals = []
                    for p in precos_encontrados:
                        num = float(p.replace('.', '').replace(',', '.'))
                        if num not in [v[0] for v in vals]:
                            vals.append((num, f"R$ {p}"))
                    
                    vals.sort() # Menor primeiro

                    if len(vals) >= 2:
                        p_por_val, p_por_str = vals[0]
                        p_de_val, p_de_str = vals[-1] # O maior é o original
                    else:
                        p_por_val, p_por_str = vals[0]
                        p_de_val, p_de_str = 0, "---"

                    # 4. FILTRO ANTI-ERRO (MOCHILA/FRALDA)
                    if p_de_val > 0:
                        calc_desc = 100 - (p_por_val / p_de_val * 100)
                        # Se a diferença entre o desconto real e o do site for gigante, ignoramos
                        if abs(calc_desc - desconto_site) > 20: continue 

                    # 5. MONTAGEM E ENVIO
                    msg = (f"📦 **OFERTA - {titulo[:90]}**\n\n"
                           f"💰 **DE {p_de_str} por {p_por_str} ({desconto_site}% OFF) 🔥**\n"
                           f"🛒 Compre: https://www.amazon.com.br/dp/{asin}?tag={AFFILIATE_TAG}")
                    
                    res = requests.post(DISCORD_WEBHOOK, json={"content": msg}, timeout=15)
                    if res.status_code < 400:
                        save_id(asin)
                        round_ids.add(asin)
                        print(f"[SUCCESS] {asin} - {p_por_str}")
                        found_count += 1
                        if found_count >= 10: break 

                except: continue
                
        except Exception as e: print(f"[ERRO] {e}")
        finally:
            browser.close()
            print(f"[FINISHED] Fim da rodada. Enviados: {found_count}")

if __name__ == "__main__":
    run()
