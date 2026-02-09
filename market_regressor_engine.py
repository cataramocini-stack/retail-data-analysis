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
    print("[START] Market Regressor — Versão Anti-Bug Preços")
    print("=" * 60)
    
    processed_ids = load_processed_ids()
    round_ids = set()
    found_count = 0
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        context = browser.new_context(user_agent=ua, viewport={'width': 1280, 'height': 2000})
        page = context.new_page()
        
        try:
            print("[POLLING] Acessando Amazon...")
            page.goto("https://www.amazon.com.br/ofertas", wait_until="load", timeout=60000)
            
            print("[SCROLLING] Carregando mais ofertas...")
            for _ in range(5):
                page.mouse.wheel(0, 1500)
                page.wait_for_timeout(2000)
            
            cards = page.query_selector_all("[data-testid='grid-desktop-item']")
            
            for card in cards:
                try:
                    # 1. Captura o Link e ASIN
                    link_el = card.query_selector("a[href*='/dp/']")
                    if not link_el: continue
                    asin = re.search(r'/([A-Z0-9]{10})', link_el.get_attribute("href")).group(1)
                    if asin in processed_ids or asin in round_ids: continue

                    # 2. Captura o Título
                    img = card.query_selector("img")
                    titulo = img.get_attribute("alt") if img else ""
                    if len(titulo) < 15: continue

                    # 3. Captura o Desconto anunciado pelo site (ex: 21%)
                    card_text = card.inner_text()
                    d_match = re.search(r'(\d+)%', card_text)
                    if not d_match: continue
                    desconto_site = int(d_match.group(1))

                    # 4. CAPTURA DE PREÇOS PRECISA (O segredo da correção)
                    # Busca o preço riscado (Preço "DE")
                    p_de_el = card.query_selector(".a-text-strike")
                    # Busca o preço atual (Preço "POR")
                    p_por_el = card.query_selector(".a-price .a-offscreen")
                    
                    if not p_por_el: continue
                    
                    p_por_str = p_por_el.inner_text().replace('R$', '').strip()
                    p_por_val = float(p_por_str.replace('.', '').replace(',', '.'))
                    
                    p_de_val = 0
                    p_de_display = "---"
                    
                    if p_de_el:
                        p_de_str = p_de_el.inner_text().replace('R$', '').strip()
                        p_de_val = float(p_de_str.replace('.', '').replace(',', '.'))
                        p_de_display = f"R$ {p_de_str}"

                    # 5. VALIDAÇÃO DE SEGURANÇA (Matemática do Desconto)
                    if p_de_val > 0:
                        # Calcula qual seria o desconto real baseado nos preços capturados
                        calculo_desc = 100 - (p_por_val / p_de_val * 100)
                        
                        # Se o desconto calculado for absurdamente diferente do anunciado (erro de leitura)
                        # Ex: Site diz 21%, mas o cálculo deu 85% (mochila de 300 por 44) -> Pula o item.
                        if abs(calculo_desc - desconto_site) > 10:
                            print(f"[SKIP] Erro de leitura em: {titulo[:30]} (Cálculo não bate)")
                            continue
                    else:
                        # Se não achou o preço "DE", mas o desconto é alto e o preço é baixo demais, ignora.
                        if desconto_site > 15 and p_por_val < 50: continue

                    # 6. ENVIO
                    msg = (f"📦 **OFERTA - {titulo[:95]}**\n\n"
                           f"💰 **DE {p_de_display} por R$ {p_por_str} ({desconto_site}% OFF) 🔥**\n"
                           f"🛒 Link: https://www.amazon.com.br/dp/{asin}?tag={AFFILIATE_TAG}")
                    
                    res = requests.post(DISCORD_WEBHOOK, json={"content": msg}, timeout=15)
                    if res.status_code < 400:
                        save_id(asin)
                        round_ids.add(asin)
                        print(f"[SUCCESS] {titulo[:30]}")
                        found_count += 1
                        if found_count >= 10: break 

                except Exception as e:
                    continue
                
        except Exception as e: print(f"[ERRO] {e}")
        finally:
            browser.close()
            print(f"[FINISHED] Enviados: {found_count}")

if __name__ == "__main__":
    run()
