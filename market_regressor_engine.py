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
    print("[START] Market Regressor — Versão Estável Anti-Erro")
    print("=" * 60)
    
    processed_ids = load_processed_ids()
    round_ids = set()
    found_count = 0
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # User agents variados para evitar ser detectado como bot simples
        uas = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        ]
        context = browser.new_context(user_agent=random.choice(uas), viewport={'width': 1280, 'height': 2500})
        page = context.new_page()
        
        try:
            print("[POLLING] Acessando Amazon...")
            # 'networkidle' espera a página carregar todas as ofertas e scripts
            page.goto("https://www.amazon.com.br/ofertas", wait_until="networkidle", timeout=90000)
            
            print("[SCROLLING] Carregando mais ofertas...")
            for _ in range(5):
                page.mouse.wheel(0, 1500)
                page.wait_for_timeout(2500)
            
            # Garante que os cards estão na tela antes de ler
            print("[WAITING] Localizando produtos...")
            page.wait_for_selector("[data-testid='grid-desktop-item']", timeout=15000)
            
            cards = page.query_selector_all("[data-testid='grid-desktop-item']")
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
                    if len(titulo) < 15: continue

                    # 3. Captura o Desconto anunciado (ex: 21%)
                    card_text = card.inner_text()
                    d_match = re.search(r'(\d+)%', card_text)
                    if not d_match: continue
                    desconto_site = int(d_match.group(1))

                    # 4. CAPTURA DE PREÇOS (O CORAÇÃO DO BUG)
                    # Procuramos o preço 'DE' (riscado)
                    p_de_el = card.query_selector(".a-text-strike")
                    # Procuramos o preço 'POR' (atual)
                    p_por_el = card.query_selector(".a-price .a-offscreen")
                    
                    if not p_por_el: continue
                    
                    # Limpeza de texto e conversão para float
                    p_por_str = p_por_el.inner_text().replace('R$', '').replace('\xa0', '').strip()
                    p_por_val = float(p_por_str.replace('.', '').replace(',', '.'))
                    
                    p_de_val = 0
                    p_de_display = "---"
                    
                    if p_de_el:
                        p_de_str = p_de_el.inner_text().replace('R$', '').replace('\xa0', '').strip()
                        p_de_val = float(p_de_str.replace('.', '').replace(',', '.'))
                        p_de_display = f"R$ {p_de_str}"

                    # 5. VALIDAÇÕES DE SEGURANÇA (FILTRO ANTI-ERRO)
                    if p_de_val > 0:
                        calculo_desc = 100 - (p_por_val / p_de_val * 100)
                        # Se a conta der um desconto absurdo que não bate com o site, ignoramos
                        # Isso mata o erro do Painel de TV por R$ 10,79
                        if abs(calculo_desc - desconto_site) > 12:
                            continue
                    else:
                        # Se não achou o preço riscado, mas o preço atual é suspeito para o item
                        if p_por_val < 30 and any(x in titulo.lower() for x in ['mochila', 'painel', 'fralda', 'tv']):
                            continue

                    # 6. MONTAGEM E ENVIO
                    msg = (f"📦 **OFERTA - {titulo[:95]}**\n\n"
                           f"💰 **DE {p_de_display} por R$ {p_por_str} ({desconto_site}% OFF) 🔥**\n"
                           f"🛒 Link: https://www.amazon.com.br/dp/{asin}?tag={AFFILIATE_TAG}")
                    
                    res = requests.post(DISCORD_WEBHOOK, json={"content": msg}, timeout=15)
                    if res.status_code < 400:
                        save_id(asin)
                        round_ids.add(asin)
                        print(f"[SUCCESS] {titulo[:35]}...")
                        found_count += 1
                        if found_count >= 10: break 

                except Exception:
                    continue
                
        except Exception as e: 
            print(f"[ERRO] Falha crítica: {e}")
        finally:
            browser.close()
            print(f"[FINISHED] Rodada encerrada. Enviados: {found_count}")

if __name__ == "__main__":
    run()
