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
MIN_DISCOUNT = 15 

def load_processed_ids():
    if not os.path.exists(METADATA_STORE): return set()
    with open(METADATA_STORE, "r") as f:
        return set(line.strip() for line in f)

def save_id(asin):
    with open(METADATA_STORE, "a") as f:
        f.write(f"{asin}\n")

def send_to_discord(item):
    frase = (
        f"📦 **OFERTA - {item['titulo']} - "
        f"DE {item['preco_de']} por {item['preco_por']} "
        f"({item['desconto']}% OFF) 🔥**"
    )
    payload = {"content": f"{frase}\n{item['url']}?tag={AFFILIATE_TAG}"}
    try:
        requests.post(DISCORD_WEBHOOK, json=payload, timeout=15)
        return True
    except: return False

def run():
    print("=" * 60)
    print("[START] Market Regressor — Correção de Sintaxe")
    print("=" * 60)
    
    processed_ids = load_processed_ids()
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        try:
            page.goto("https://www.amazon.com.br/ofertas", wait_until="load", timeout=90000)
            
            print("[INFO] Estabilizando elementos...")
            for _ in range(2):
                page.mouse.wheel(0, 1000)
                page.wait_for_timeout(2000)
            
            # Mira lógica: DIVs que possuem links de produtos
            cards = page.query_selector_all("div:has(a[href*='/dp/'])")
            print(f"[INFO] Candidatos detectados: {len(cards)}")
            
            found_count = 0
            for card in cards:
                try:
                    texto_card = card.inner_text()
                    
                    # Busca ASIN
                    link_el = card.query_selector("a[href*='/dp/']")
                    url_raw = link_el.get_attribute("href")
                    asin_match = re.search(r'/([A-Z0-9]{10})(?:[/?]|$)', url_raw)
                    if not asin_match: continue
                    asin = asin_match.group(1)
                    
                    if asin in processed_ids: continue

                    # Busca Desconto
                    desc_match = re.search(r'(\d+)%', texto_card)
                    if not desc_match: continue
                    desconto = int(desc_match.group(1))
                    if desconto < MIN_DISCOUNT: continue

                    # Limpeza de Título
                    linhas = [l.strip() for l in texto_card.split('\n') if len(l.strip()) > 5]
                    titulo = "Oferta Amazon"
                    for linha in linhas:
                        if any(x in linha.lower() for x in ["r$", "%", "prime", "oferta", "termina"]): continue
