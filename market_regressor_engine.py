import os
import time
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
import requests

load_dotenv()

# Configurações
DISCORD_WEBHOOK = os.getenv("INGESTION_ENDPOINT_PRIMARY")
AFFILIATE_TAG = os.getenv("AFFILIATION_DATA_METRIC", "scriptoriu01a-20")
MIN_DISCOUNT = 5  # Filtro de 5% para teste

def send_to_discord(product):
    payload = {
        "content": f"🚨 **OFERTA ENCONTRADA!**\n📦 **{product['title']}**\n💰 Preço: {product['price']}\n📉 Desconto: {product['discount']}%\n🔗 Link: {product['link']}?tag={AFFILIATE_TAG}"
    }
    try:
        requests.post(DISCORD_WEBHOOK, json=payload)
    except Exception as e:
        print(f"[ERRO] Falha ao enviar para o Discord: {e}")

def run():
    print("============================================================")
    print("[START] Market Regressor — Mira Calibrada v2")
    print("============================================================")
    
    with sync_playwright() as p:
        # Lançando o navegador
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        # Aumentando o timeout da página para 90 segundos
        page.set_default_timeout(90000)
        
        print(f"[POLLING] Acessando Amazon Ofertas...")
        try:
            # Estratégia domcontentloaded é mais rápida e estável em servidores
            page.goto("https://www.amazon.com.br/ofertas", wait_until="domcontentloaded")
            
            # Espera forçada de 10 segundos para o JavaScript da Amazon montar a vitrine
            print("[INFO] Aguardando carregamento dos produtos...")
            page.wait_for_timeout(10000)
            
            # Tira um print para a gente ver se o site carregou ou se deu erro
            page.
