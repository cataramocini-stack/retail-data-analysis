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
    print("[START] Market Regressor — Estabilidade Máxima")
    print("=" * 60)
    
    processed_ids = load_processed_ids()
    round_ids = set()
    found_count = 0
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        uas = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        ]
        context = browser.new_context(user_agent=random.choice(uas), viewport={'width': 1280, 'height': 2500})
        page = context.new_page()
        
        try:
            print("[POLLING] Acessando Amazon...")
            # Mudado para 'domcontentloaded' para evitar o Timeout da rede
            page.goto("https://www.amazon.com.br/ofertas", wait_until="domcontentloaded", timeout=60000)
            
            # Espera manual curta para os primeiros itens aparecerem
            page.wait_for_timeout(5000)
            
            print("[SCROLLING] Carregando mais ofertas...")
            for _ in range(5):
                page.mouse.wheel(0, 1500)
                page.wait_for_timeout(2000)
            
            # Tenta localizar os cards (seletor principal e alternativo)
            cards = page.query_selector_all("[data-testid='grid-desktop-item']")
            if not cards:
                cards = page.query_selector_all(".a-section.oct-desktop-grid-item")
            
            print(f"[INFO] Total de elementos detectados: {len(cards)}")
            
            for card in cards:
                try:
                    link_el = card.query_selector("a[href*='/dp/']")
                    if not link_el: continue
                    href = link_el.get_attribute("href")
                    asin_match = re.search(r'/([A-Z0-9]{10})', href)
                    if not asin_match: continue
                    asin = asin_match.group(1)

                    if asin in processed_ids or asin in round_ids: continue

                    img = card.query_selector("img")
                    titulo = img.get_attribute("alt") if img else ""
                    if len(titulo) < 15: continue

                    card_text = card.inner_text()
                    d_match = re.search(r'(\d+)%', card_text)
                    if not d_match: continue
                    desconto_site = int(d_match.group(1))

                    # Lógica de Captura de Preço Refinada
                    p_de_el = card.query_selector(".a-text-strike")
                    p_por_el = card.query_selector(".a-price .a-offscreen")
                    
                    # Se não achou pelo seletor clássico, tenta pegar do texto bruto como último recurso
                    if not p_por_el:
                        precos_brutos = re.findall(r'R\$\s?([\d\.]+,[\d]{2})', card_text)
                        if not precos_brutos: continue
                        p_por_val = float(precos_brutos[0].replace('.', '').replace(',', '.'))
                        p_por_str = precos_brutos[0]
                    else:
                        p_por_str = p_por_el.inner_text().replace('R$', '').replace('\xa0', '').strip()
                        p_por_val = float(p_por_str.replace('.', '').replace(',', '.'))
                    
                    p_de_val = 0
                    p_de_display = "---"
                    
                    if p_de_el:
                        p_de_str = p_de_el.inner_text().replace('R$', '').replace('\xa0', '').strip()
                        p_de_val = float(p_de_str.replace('.', '').replace(',', '.'))
                        p_de_display = f"R$ {p_de_str}"

                    # PROVA REAL: Evita erros de mochila/painel/fralda
                    if p_de_val > 0:
                        calc_desc = 100 - (p_por_val / p_de_val * 100)
                        if abs(calc_desc - desconto_site) > 15:
                            continue # Matemática furada = Dado errado capturado
                    
                    # Filtro de preço mínimo para itens grandes
                    if p_por_val < 30 and any(x in titulo.lower() for x in ['mochila', 'painel', 'fralda', 'tv', 'cadeira']):
                        continue

                    msg = (f"📦 **OFERTA - {titulo[:95]}**\n\n"
                           f"💰 **DE {p_de_display} por R$ {p_por_str} ({desconto_site}% OFF) 🔥**\n"
                           f"🛒 Link: https://www.amazon.com.br/dp/{asin}?tag={AFFILIATE_TAG}")
                    
                    res = requests.post(DISCORD_WEBHOOK, json={"content": msg}, timeout=15)
                    if res.status_code < 400:
                        save_id(asin)
                        round_ids.add(asin)
                        print(f"[SUCCESS] {asin} - {titulo[:30]}")
                        found_count += 1
                        if found_count >= 10: break 

                except Exception:
                    continue
                
        except Exception as e: 
            print(f"[ERRO] Falha: {e}")
        finally:
            browser.close()
            print(f"[FINISHED] Enviados: {found_count}")

if __name__ == "__main__":
    run()
