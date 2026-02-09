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
    print("[START] Market Regressor — Versão Final Estabilizada")
    print("=" * 60)
    
    processed_ids = load_processed_ids()
    round_ids = set()
    found_count = 0 # Inicializado aqui para evitar erro de variável
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # User-agent atualizado
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        context = browser.new_context(user_agent=ua, viewport={'width': 1280, 'height': 720})
        page = context.new_page()
        
        try:
            print("[POLLING] Acessando Amazon...")
            # Mudança: 'load' é mais rápido e menos propenso a timeout que 'networkidle'
            page.goto("https://www.amazon.com.br/ofertas", wait_until="load", timeout=60000)
            
            page.wait_for_timeout(5000)
            page.mouse.wheel(0, 800)
            page.wait_for_timeout(3000)
            
            # Busca por links de produtos
            cards = page.query_selector_all("div:has(a[href*='/dp/'])")
            print(f"[INFO] Elementos detectados: {len(cards)}")
            
            for card in cards:
                try:
                    link_el = card.query_selector("a[href*='/dp/']")
                    if not link_el: continue
                    
                    href = link_el.get_attribute("href")
                    asin_match = re.search(r'/([A-Z0-9]{10})', href)
                    if not asin_match: continue
                    asin = asin_match.group(1)
                    
                    if asin in processed_ids or asin in round_ids: continue

                    txt = card.inner_text()
                    d_match = re.search(r'(\d+)%', txt)
                    if not d_match: continue
                    desconto = d_match.group(1)
                    if int(desconto) < 15: continue

                    # Título via ALT da imagem (o mais limpo)
                    img = card.query_selector("img")
                    titulo = img.get_attribute("alt") if img else ""
                    if len(titulo) < 10: continue

                    # Preços
                    precos = re.findall(r'R\$\s?[\d.,]+', txt)
                    vals = []
                    for p_raw in precos:
                        try:
                            v = float(p_raw.replace('R$', '').replace('.', '').replace(',', '.').strip())
                            if v not in [x[0] for x in vals]: vals.append((v, p_raw))
                        except: continue
                    
                    if not vals: continue
                    vals.sort()
                    p_por = vals[0][1]
                    p_de = vals[-1][1] if len(vals) > 1 else "---"

                    # Formatação idêntica ao seu pedido
                    msg = (f"📦 **OFERTA - {titulo[:90]} - "
                           f"DE {p_de} por {p_por} ({desconto}% OFF) 🔥**\n"
                           f"https://www.amazon.com.br/dp/{asin}?tag={AFFILIATE_TAG}")
                    
                    res = requests.post(DISCORD_WEBHOOK, json={"content": msg}, timeout=15)
                    if res.status_code < 400:
                        save_id(asin)
                        round_ids.add(asin)
                        print(f"[SUCCESS] {titulo[:30]}")
                        found_count += 1
                        if found_count >= 5: break
                except: continue
                
        except Exception as e:
            print(f"[ERRO] {e}")
        finally:
            browser.close()
            print(f"[FINISHED] Enviados: {found_count}")

if __name__ == "__main__":
    run()
