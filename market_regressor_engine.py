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
    print("[START] Market Regressor — Versão Ultra Resiliente")
    print("=" * 60)
    
    processed_ids = load_processed_ids()
    round_ids = set()
    found_count = 0
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # User agents mais modernos para evitar bloqueios
        uas = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ]
        context = browser.new_context(user_agent=random.choice(uas), viewport={'width': 1920, 'height': 1080})
        page = context.new_page()
        
        try:
            print("[POLLING] Acessando Amazon Brasil...")
            # Tentativa de acesso com tempo de espera generoso
            page.goto("https://www.amazon.com.br/ofertas", wait_until="domcontentloaded", timeout=60000)
            
            # --- AGUARDAR RENDERIZAÇÃO ---
            print("[WAITING] Aguardando produtos carregarem...")
            page.wait_for_timeout(7000) # 7 segundos iniciais

            # Tenta múltiplos seletores de cards da Amazon (eles mudam conforme o teste A/B deles)
            selectors = [
                "[data-testid='grid-desktop-item']",
                ".a-section.oct-desktop-grid-item",
                "div[id^='grid-desktop-item-']",
                "div:has(a[href*='/dp/'])"
            ]
            
            # Scroll Progressivo
            print("[SCROLLING] Executando Deep Scroll...")
            for _ in range(5):
                page.mouse.wheel(0, 1500)
                page.wait_for_timeout(2000)

            # Captura de cards usando qualquer um dos seletores conhecidos
            cards = []
            for sel in selectors:
                found_cards = page.query_selector_all(sel)
                if len(found_cards) > 5:
                    cards = found_cards
                    print(f"[INFO] Seletor de sucesso: {sel}")
                    break
            
            print(f"[INFO] Total de elementos detectados: {len(cards)}")
            
            for card in cards:
                try:
                    # 1. Captura Link e ASIN
                    link_el = card.query_selector("a[href*='/dp/']")
                    if not link_el: continue
                    href = link_el.get_attribute("href")
                    asin_match = re.search(r'/([A-Z0-9]{10})', href)
                    if not asin_match: continue
                    asin = asin_match.group(1)

                    if asin in processed_ids or asin in round_ids: continue

                    # 2. Captura Título
                    img = card.query_selector("img")
                    titulo = img.get_attribute("alt") if img else ""
                    if len(titulo) < 10: continue

                    # 3. Captura o Desconto do Site
                    card_text = card.inner_text()
                    d_match = re.search(r'(\d+)%', card_text)
                    desconto_site = int(d_match.group(1)) if d_match else 0

                    # 4. CAPTURA DE PREÇOS (PROVA REAL)
                    # Tentamos o método visual (HTML) primeiro
                    p_de_el = card.query_selector(".a-text-strike")
                    p_por_el = card.query_selector(".a-price .a-offscreen")
                    
                    p_por_val = 0
                    p_de_val = 0

                    if p_por_el:
                        p_por_str = p_por_el.inner_text().replace('R$', '').replace('\xa0', '').strip()
                        p_por_val = float(p_por_str.replace('.', '').replace(',', '.'))
                        p_por_display = f"R$ {p_por_str}"
                    else:
                        # Fallback para regex no texto do card
                        precos_brutos = re.findall(r'R\$\s?([\d\.]+,[\d]{2})', card_text)
                        if not precos_brutos: continue
                        p_por_val = float(precos_brutos[0].replace('.', '').replace(',', '.'))
                        p_por_display = f"R$ {precos_brutos[0]}"

                    if p_de_el:
                        p_de_str = p_de_el.inner_text().replace('R$', '').replace('\xa0', '').strip()
                        p_de_val = float(p_de_str.replace('.', '').replace(',', '.'))
                        p_de_display = f"R$ {p_de_str}"
                    else:
                        p_de_display = "---"

                    # 5. BLOQUEADOR DE ERROS (A sua prova real)
                    if p_de_val > 0 and desconto_site > 0:
                        calc_desc = 100 - (p_por_val / p_de_val * 100)
                        if abs(calc_desc - desconto_site) > 15:
                            # Se a conta de padeiro não bater com o site, ignoramos (evita o erro da mochila/fralda)
                            continue 
                    
                    if p_por_val < 30 and any(x in titulo.lower() for x in ['fralda', 'mochila', 'painel', 'tv']):
                        continue

                    # 6. ENVIO
                    msg = (f"📦 **OFERTA - {titulo[:90]}**\n\n"
                           f"💰 **DE {p_de_display} por {p_por_display} ({desconto_site}% OFF) 🔥**\n"
                           f"🛒 Compre: https://www.amazon.com.br/dp/{asin}?tag={AFFILIATE_TAG}")
                    
                    res = requests.post(DISCORD_WEBHOOK, json={"content": msg}, timeout=15)
                    if res.status_code < 400:
                        save_id(asin)
                        round_ids.add(asin)
                        print(f"[SUCCESS] {asin} enviado.")
                        found_count += 1
                        if found_count >= 10: break 

                except Exception:
                    continue
                
        except Exception as e: 
            print(f"[ERRO] {e}")
        finally:
            browser.close()
            print(f"[FINISHED] Fim da rodada. Itens enviados: {found_count}")

if __name__ == "__main__":
    run()
