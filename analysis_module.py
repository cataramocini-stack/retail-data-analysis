# -*- coding: utf-8 -*-
"""
Retail Data Analysis - Módulo de Análise de Promoções
Busca as melhores ofertas na Amazon Brasil e envia para o Webhook configurado.
"""

import os
import re
import json
import subprocess
import requests
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync

# Carrega variáveis de ambiente do arquivo .env (desenvolvimento local)
load_dotenv()

# Segredos lidos das variáveis de ambiente
TARGET_URL = os.getenv("TARGET_URL")
PARTNER_CODE = os.getenv("PARTNER_CODE")

# Caminho do arquivo de persistência
LOGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs.dat")

# URL alvo
AMAZON_OFERTAS_URL = "https://www.amazon.com.br/ofertas"

# Desconto mínimo para considerar (em porcentagem)
DESCONTO_MINIMO = 20


def carregar_ids_enviados():
    """Carrega os IDs já enviados do arquivo logs.dat."""
    if not os.path.exists(LOGS_FILE):
        return set()
    with open(LOGS_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())


def salvar_id_enviado(deal_id):
    """Salva um novo ID no arquivo logs.dat."""
    with open(LOGS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{deal_id}\n")
    print(f"💾 ID salvo em logs.dat: {deal_id}")


def git_commit_automatico():
    """Faz commit automático do logs.dat no repositório."""
    try:
        repo_dir = os.path.dirname(os.path.abspath(__file__))
        subprocess.run(["git", "config", "user.name", "Retail Bot"], cwd=repo_dir, check=True)
        subprocess.run(["git", "config", "user.email", "bot@retail-analysis.local"], cwd=repo_dir, check=True)
        subprocess.run(["git", "add", "logs.dat"], cwd=repo_dir, check=True)
        resultado = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=repo_dir,
            capture_output=True,
        )
        if resultado.returncode != 0:
            subprocess.run(
                ["git", "commit", "-m", "🔄 Atualiza logs.dat com nova oferta enviada"],
                cwd=repo_dir,
                check=True,
            )
            subprocess.run(["git", "push"], cwd=repo_dir, check=True)
            print("✅ Commit e push realizados com sucesso!")
        else:
            print("ℹ️ Nenhuma alteração em logs.dat para commitar.")
    except subprocess.CalledProcessError as e:
        print(f"❌ Erro ao fazer git commit/push: {e}")


def extrair_porcentagem(texto):
    """Extrai o valor numérico de porcentagem de uma string."""
    match = re.search(r"(\d+)\s*%", texto)
    if match:
        return int(match.group(1))
    return 0


def buscar_ofertas():
    """Usa Playwright + Stealth para buscar ofertas na Amazon Brasil."""
    print("🔍 Iniciando busca de ofertas na Amazon Brasil...")
    ofertas = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="pt-BR",
            viewport={"width": 1920, "height": 1080},
        )
        page = context.new_page()
        stealth_sync(page)

        try:
            page.goto(AMAZON_OFERTAS_URL, wait_until="networkidle", timeout=90000)
            print("📄 Página de ofertas carregada com sucesso!")

            # Screenshot de debug para verificar o que o robô está vendo
            debug_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug.png")
            page.screenshot(path=debug_path, full_page=False)
            print(f"📸 Screenshot de debug salvo em: {debug_path}")

            # Aguarda conteúdo dinâmico renderizar
            page.wait_for_timeout(8000)

            # Scroll para carregar mais ofertas
            for _ in range(5):
                page.evaluate("window.scrollBy(0, window.innerHeight)")
                page.wait_for_timeout(2000)

            # Log do HTML para debug dos seletores
            page_title = page.title()
            print(f"📋 Título da página: {page_title}")

            # Estratégia 1: Container principal de ofertas
            cards = page.query_selector_all(
                '[data-testid="grid-deals-container"] > div, '
                '[data-testid="deal-card"]'
            )
            print(f"📦 Estratégia 1 (data-testid): {len(cards)} cards")

            # Estratégia 2: Seletores genéricos de grid de ofertas
            if len(cards) == 0:
                cards = page.query_selector_all(
                    'div[class*="DealCard"], '
                    'div[class*="deal-card"], '
                    'div[class*="dealCard"]'
                )
                print(f"📦 Estratégia 2 (DealCard classes): {len(cards)} cards")

            # Estratégia 3: Seletores Amazon clássicos
            if len(cards) == 0:
                cards = page.query_selector_all(
                    '.shoveler-cell, '
                    '.a-list-item, '
                    'div[data-deal-id], '
                    'div[id*="deal"], '
                    'li[class*="deal"]'
                )
                print(f"📦 Estratégia 3 (shoveler/list-item/deal): {len(cards)} cards")

            # Estratégia 4: Links de produto com desconto visível
            if len(cards) == 0:
                cards = page.query_selector_all(
                    'div.a-section a[href*="/dp/"], '
                    'div.a-section a[href*="/deal/"], '
                    'div.a-cardui'
                )
                print(f"📦 Estratégia 4 (links dp/deal/cardui): {len(cards)} cards")

            # Estratégia 5: Último recurso — qualquer bloco com texto de porcentagem
            if len(cards) == 0:
                all_sections = page.query_selector_all('div.a-section')
                cards = []
                for sec in all_sections:
                    txt = sec.inner_text()
                    if "%" in txt and ("OFF" in txt.upper() or "DESCONTO" in txt.upper() or "R$" in txt):
                        cards.append(sec)
                print(f"📦 Estratégia 5 (texto com %/OFF/R$): {len(cards)} cards")

            print(f"\n📦 Total de cards encontrados: {len(cards)}")

            for i, card in enumerate(cards):
                try:
                    card_text = card.inner_text()

                    # Extrai porcentagem de desconto do texto do card
                    porcentagem = extrair_porcentagem(card_text)

                    if porcentagem <= DESCONTO_MINIMO:
                        continue

                    # Tenta extrair o título
                    titulo_el = card.query_selector(
                        'span[class*="title"], '
                        'a[class*="title"], '
                        'span.a-truncate-full, '
                        'div[class*="Title"], '
                        'span.a-text-normal, '
                        'a span'
                    )
                    titulo = titulo_el.inner_text().strip() if titulo_el else ""
                    if not titulo:
                        # Tenta pegar a primeira linha significativa do texto
                        linhas = [l.strip() for l in card_text.split("\n") if len(l.strip()) > 10]
                        titulo = linhas[0] if linhas else f"Oferta #{i+1}"

                    # Tenta extrair o link
                    link_el = card.query_selector('a[href*="/dp/"], a[href*="/deal/"], a[href]')
                    link = ""
                    deal_id = f"deal_{i}_{porcentagem}"
                    if link_el:
                        href = link_el.get_attribute("href")
                        if href:
                            if href.startswith("/"):
                                href = f"https://www.amazon.com.br{href}"
                            link = href
                            # Extrai o ASIN ou deal ID da URL
                            asin_match = re.search(r"/dp/([A-Z0-9]{10})", href)
                            deal_match = re.search(r"dealid=([^&]+)", href, re.IGNORECASE)
                            if asin_match:
                                deal_id = asin_match.group(1)
                            elif deal_match:
                                deal_id = deal_match.group(1)

                    # Tenta extrair preço
                    preco_el = card.query_selector(
                        'span.a-price span.a-offscreen, '
                        'span.a-price-whole, '
                        'span[class*="price"]'
                    )
                    preco = preco_el.inner_text().strip() if preco_el else ""
                    if not preco:
                        preco_match = re.search(r"R\$\s*[\d.,]+", card_text)
                        preco = preco_match.group(0) if preco_match else "Preço não disponível"

                    # Tenta extrair imagem
                    img_el = card.query_selector("img[src]")
                    img_url = img_el.get_attribute("src") if img_el else ""

                    ofertas.append({
                        "id": deal_id,
                        "titulo": titulo,
                        "desconto": porcentagem,
                        "preco": preco,
                        "link": link,
                        "imagem": img_url,
                    })

                    print(f"  🏷️ {titulo[:60]}... → {porcentagem}% OFF")

                except Exception as e:
                    print(f"  ⚠️ Erro ao processar card #{i}: {e}")
                    continue

        except Exception as e:
            print(f"❌ Erro ao acessar a página de ofertas: {e}")
        finally:
            browser.close()

    print(f"🔎 Total de ofertas com mais de {DESCONTO_MINIMO}% de desconto: {len(ofertas)}")
    return ofertas


def montar_link_afiliado(link):
    """Adiciona a tag de afiliado ao link do produto."""
    if not link or not PARTNER_CODE:
        return link
    separador = "&" if "?" in link else "?"
    return f"{link}{separador}tag={PARTNER_CODE}"


def enviar_para_webhook(oferta):
    """Envia a oferta para o Webhook (Discord) configurado."""
    if not TARGET_URL:
        print("❌ TARGET_URL não configurada! Defina a variável de ambiente.")
        return False

    link_afiliado = montar_link_afiliado(oferta["link"])

    embed = {
        "title": f"🔥 {oferta['desconto']}% OFF — {oferta['titulo'][:200]}",
        "url": link_afiliado,
        "color": 0xFF4500,
        "fields": [
            {"name": "💰 Preço", "value": oferta["preco"], "inline": True},
            {"name": "📉 Desconto", "value": f"{oferta['desconto']}%", "inline": True},
        ],
        "footer": {"text": "Retail Data Analysis • Amazon BR"},
    }

    if oferta.get("imagem"):
        embed["thumbnail"] = {"url": oferta["imagem"]}

    if link_afiliado:
        embed["fields"].append(
            {"name": "🔗 Link", "value": f"[Acessar oferta]({link_afiliado})", "inline": False}
        )

    payload = {"embeds": [embed]}

    try:
        response = requests.post(
            TARGET_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        if response.status_code == 204:
            print(f"✅ Oferta enviada com sucesso para o Webhook!")
            return True
        else:
            print(f"❌ Erro ao enviar para Webhook: HTTP {response.status_code} - {response.text}")
            return False
    except requests.RequestException as e:
        print(f"❌ Erro de conexão com o Webhook: {e}")
        return False


def main():
    """Fluxo principal do módulo de análise."""
    print("=" * 60)
    print("🚀 Retail Data Analysis — Iniciando execução...")
    print("=" * 60)

    # Validação das variáveis de ambiente
    if not TARGET_URL:
        print("❌ Variável TARGET_URL não definida. Abortando.")
        return
    if not PARTNER_CODE:
        print("⚠️ Variável PARTNER_CODE não definida. Links sem tag de afiliado.")

    # Busca ofertas
    ofertas = buscar_ofertas()

    if not ofertas:
        print("😕 Nenhuma oferta encontrada com desconto acima de 20%. Encerrando.")
        return

    # Ordena pelo maior desconto e seleciona a melhor
    ofertas.sort(key=lambda x: x["desconto"], reverse=True)
    melhor_oferta = ofertas[0]

    print(f"\n🏆 Melhor oferta encontrada:")
    print(f"   📌 {melhor_oferta['titulo'][:80]}")
    print(f"   📉 Desconto: {melhor_oferta['desconto']}%")
    print(f"   💰 Preço: {melhor_oferta['preco']}")

    # Verifica se já foi postada
    ids_enviados = carregar_ids_enviados()
    if melhor_oferta["id"] in ids_enviados:
        print(f"\n⚠️ Oferta já postada anteriormente (ID: {melhor_oferta['id']}). Pulando.")
        # Tenta a próxima oferta não postada
        oferta_nova = None
        for oferta in ofertas:
            if oferta["id"] not in ids_enviados:
                oferta_nova = oferta
                break

        if not oferta_nova:
            print("😕 Todas as ofertas já foram postadas. Encerrando.")
            return

        melhor_oferta = oferta_nova
        print(f"\n🆕 Nova oferta selecionada:")
        print(f"   📌 {melhor_oferta['titulo'][:80]}")
        print(f"   📉 Desconto: {melhor_oferta['desconto']}%")

    # Envia para o Webhook
    sucesso = enviar_para_webhook(melhor_oferta)

    if sucesso:
        salvar_id_enviado(melhor_oferta["id"])
        git_commit_automatico()

    print("\n" + "=" * 60)
    print("✅ Execução finalizada!")
    print("=" * 60)


if __name__ == "__main__":
    main()
