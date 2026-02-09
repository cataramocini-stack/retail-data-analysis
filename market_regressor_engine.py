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
    print("[START] Market Regressor — Deep Scroll Stable Edition")
    print("=" * 60)
    
    processed_ids = load_processed_ids()
    round_ids = set()
    found_count = 0
    
    with sync_playwright() as p:
        # Lançando o navegador
        browser = p.chromium.launch(headless=True)
        
        # Lista de User-Agents para rotacionar e evitar bloqueios
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        ]
        
        context = browser.new_context(
            user_agent=random.choice(user_agents),
            viewport={'width': 1280, 'height': 3000}
        )
        page = context.new_page()
        
        try:
            print("[POLLING] Acessando Amazon...")
            page.goto("https://www.amazon.com.br/ofertas", wait_until="networkidle", timeout=60000)
            
            # --- DEEP SCROLL INTELIGENTE ---
            print("[SCROLLING] Carregando ofertas...")
            for i in range(5):
                page.mouse.wheel(0, 1200)
                page.wait_for_timeout(2000) # Espera o conteúdo "renderizar"
            
            # Espera forçada por um seletor de produto
            page.wait_for_selector("[data-testid='grid-desktop-item']", timeout=15000)
            
            # Captura de elementos (usa dois seletores por segurança)
            cards = page.query_selector_all("[data-testid='grid-desktop-item']")
            if not cards:
                cards = page.query_selector_all("div[id^='grid-desktop-item-']")
                
            print(f"[INFO] Elementos detectados: {len(cards)}")
            
            for card in cards:
                try:
                    # Tentar pegar o link do produto
                    link_el = card.query_selector("a[href*='/dp/']")
                    if not link_el: continue
                    
                    href = link_el.get_attribute("href")
                    asin_match = re.search(r'/([A-Z0-9]{10})', href)
                    if not asin_match: continue
                    asin = asin_match.group(1)

                    if asin in processed_ids or asin in round_ids: continue

                    # Título
                    img = card.query_selector("img")
                    titulo = img.get_attribute("alt") if img else ""
                    if len(titulo) < 15: continue

                    # Filtro de texto para evitar banners genéricos
                    card_text = card.inner_text()
                    if "%" not in card_text: continue

                    # Extração de Preços
                    precos_raw = re.findall(r'R\$\s?([\d\.]+,[\d]{2})', card_text)
                    vals = []
                    for p_raw in precos_raw:
                        try:
                            num = float(p_raw.replace('.', '').replace(',', '.').strip())
                            if num > 5: vals.append((num, f"R$ {p_raw}"))
                        except: continue
                    
                    if len(vals) < 1: continue
                    vals.sort()
                    p_por_str = vals[0][1] # O menor valor encontrado
                    p_de_str = vals[-1][1] if len(vals) > 1 else "---"

                    # Montagem da Mensagem
                    msg = (f"📦 **OFERTA DETECTADA - {titulo[:95]}**\n\n"
                           f"💰 **Por apenas {p_por_str} 🔥**\n"
                           f"🛒 Link: https://www.amazon.com.br/dp/{asin}?tag={AFFILIATE_TAG}")
                    
                    # Envio
                    res = requests.post(DISCORD_WEBHOOK, json={"content": msg}, timeout=15)
                    if res.status_code < 400:
                        save_id(asin)
                        round_ids.
