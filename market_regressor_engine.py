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

def run():
    print("=" * 60)
    print("[START] Market Regressor — Mira Coringa & Título Limpo")
    print("=" * 60)
    
    processed_ids = load_processed_ids()
    round_ids = set()
    
    with sync_playwright() as p:
        # Modo 'Slow Mo' para parecer mais humano e evitar o 'Cards: 0'
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
        )
        page = context.new_page()
        
        try:
            print("[POLLING] Acessando Amazon...")
            page.goto("https://www.amazon.com.br/ofertas", wait_until="networkidle", timeout=90000)
            
            # Scroll progressivo para forçar a renderização das DIVs
            for _ in range(3):
                page.mouse.wheel(0, 1000)
                page.wait_for_timeout(2000)
            
            # MIRA CORINGA: Pega qualquer bloco que tenha cara de produto
            cards = page.query_selector_all("div[data-testid*='grid-desktop-item'], div[class*='DealGridItem'], .a-section.list-item")
            
            # Se ainda der 0, tentamos uma busca desesperada por qualquer DIV com link de produto
            if not cards:
                cards = page.query_selector_all("div:has(a[href*='/dp/'])")
                
            print(f"[INFO] Elementos detectados: {len(cards)}")
            
            found_count = 0
            for card in cards:
                try:
                    # 1. PEGAR ASIN (ID)
                    link_el = card.query_selector("a[href*='/dp/']")
                    if not link_el: continue
                    url_raw = link_el.get_attribute("href")
                    asin_match = re.search(r'/([A-Z0-9]{10})', url_raw)
                    if not asin_match: continue
                    asin = asin_match.group(1)
                    
                    if asin in processed_ids or asin in round_ids: continue

                    # 2. PEGAR DESCONTO (Símbolo %)
                    texto_card = card.inner_text()
                    desc_match = re.search(r'(\d+)%', texto_card)
                    if not desc_match: continue
                    desconto = int(desc_match.group(1))
                    if desconto < 15: continue

                    # 3. PEGAR TÍTULO (Prioridade total para o ALT da imagem - Evita 'Menor Preço')
                    img_el = card.query_selector("img")
                    titulo = img_el.get_attribute("alt") if img_el else ""
                    
                    if not titulo or len(titulo) < 15:
                        # Backup: tenta o link
                        title_el = card.query_selector(".a-truncate-cut, h3")
                        titulo = title_el.inner_text().strip() if title_el else "Produto em Oferta"

                    # 4. PREÇOS (Limpeza completa de R$)
                    precos_raw = re.findall(r'R\$\s?[\d.,]+', texto_card)
                    limpos = []
                    for pr in precos_raw:
                        val = float(pr.replace('R$', '').replace('.', '').replace(',', '.').strip())
                        if val not in [v[0] for v in limpos]: limpos.append((val, pr))
                    
                    limpos.sort() # Menor preço (Por) primeiro
                    if not limpos: continue
                    
                    preco_por = limpos[0][1]
                    preco_de = limpos[-1][1] if len(limpos) > 1 else "---"

                    # FORMATAÇÃO FINAL ESTILO PROFISSIONAL
                    frase = (
                        f"📦 **OFERTA - {titulo[:90]} - "
                        f"DE {preco_de} por {preco_por} "
                        f"({desconto}% OFF) 🔥**"
                    )
                    
                    payload = {"content": f"{frase}\nhttps://www.amazon.com.br/dp/{asin}?tag={AFFILIATE_TAG}"}
                    
                    response = requests.post(DISCORD_WEBHOOK, json=payload, timeout
