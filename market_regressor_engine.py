# -*- coding: utf-8 -*-
"""
Market Regressor Engine — Stochastic Price Volatility Analyzer
Performs multi-dimensional regression analysis on retail pricing data
sourced from publicly available e-commerce indices (BR market segment).
"""

import os
import re
import subprocess
import requests
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync

# Bootstrap runtime configuration from local environment manifest
load_dotenv()

# Primary data ingestion and affiliation metric parameters
INGESTION_ENDPOINT_PRIMARY = os.getenv("INGESTION_ENDPOINT_PRIMARY")
AFFILIATION_DATA_METRIC = os.getenv("AFFILIATION_DATA_METRIC")

# Persistent metadata store for processed data hashes
METADATA_STORE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "processed_metadata.db")

# Source URI for stochastic price sampling
SAMPLING_SOURCE_URI = "https://www.amazon.com.br/ofertas"

# Minimum variance threshold for data relevance (percentage)
VARIANCE_THRESHOLD = 20


def load_processed_hashes():
    """Deserializes previously ingested data hashes from persistent store."""
    if not os.path.exists(METADATA_STORE):
        return set()
    with open(METADATA_STORE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())


def persist_data_hash(data_hash):
    """Serializes a new data hash to the persistent metadata store."""
    with open(METADATA_STORE, "a", encoding="utf-8") as f:
        f.write(f"{data_hash}\n")
    print(f"[STORE] Data hash committed to metadata store: {data_hash}")


def synchronize_version_control():
    """Performs automated VCS synchronization of the metadata store."""
    try:
        repo_dir = os.path.dirname(os.path.abspath(__file__))
        subprocess.run(["git", "config", "user.name", "Market Regressor Bot"], cwd=repo_dir, check=True)
        subprocess.run(["git", "config", "user.email", "bot@market-regressor.local"], cwd=repo_dir, check=True)
        subprocess.run(["git", "add", "processed_metadata.db"], cwd=repo_dir, check=True)
        resultado = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=repo_dir,
            capture_output=True,
        )
        if resultado.returncode != 0:
            subprocess.run(
                ["git", "commit", "-m", "sync: update processed_metadata.db with latest regression output"],
                cwd=repo_dir,
                check=True,
            )
            subprocess.run(["git", "push"], cwd=repo_dir, check=True)
            print("[VCS] Metadata store synchronized to remote repository.")
        else:
            print("[VCS] No delta detected in metadata store. Skipping synchronization.")
    except subprocess.CalledProcessError as e:
        print(f"[VCS_ERROR] Version control synchronization failed: {e}")


def extract_variance_coefficient(text):
    """Extracts numerical variance coefficient from raw text data."""
    match = re.search(r"(\d+)\s*%", text)
    if match:
        return int(match.group(1))
    return 0


def execute_stochastic_sampling():
    """Initiates headless chromium session for stochastic price data collection."""
    print("[SAMPLING] Initializing stochastic price polling on BR market index...")
    data_points = []

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

        debug_path = os.path.join(os.getcwd(), "debug.png")

        try:
            page.goto(SAMPLING_SOURCE_URI, wait_until="domcontentloaded", timeout=60000)
            print("[SAMPLING] Source index loaded. DOM content rendered.")

            # Temporal buffer for asynchronous DOM hydration
            page.wait_for_timeout(10000)

            # Capture viewport state for diagnostic analysis
            page.screenshot(path=debug_path, full_page=True)
            print("[DIAG] Viewport snapshot captured for post-hoc analysis.")

            # Viewport traversal to trigger lazy-loaded data nodes
            for _ in range(5):
                page.evaluate("window.scrollBy(0, window.innerHeight)")
                page.wait_for_timeout(2000)

            # Selector Strategy 1 (primary): Classical DOM node extraction
            cards = page.query_selector_all(
                '.shoveler-cell, '
                '.a-list-item, '
                'div[data-deal-id], '
                'div[id*="deal"], '
                'li[class*="deal"]'
            )
            print(f"[EXTRACT] Strategy 1 (classical nodes): {len(cards)} data points localized")

            # Selector Strategy 2: TestID-annotated DOM fragments
            if len(cards) == 0:
                cards = page.query_selector_all(
                    '[data-testid="grid-deals-container"] > div, '
                    '[data-testid="deal-card"]'
                )
                print(f"[EXTRACT] Strategy 2 (testid fragments): {len(cards)} data points localized")

            # Selector Strategy 3: Class-based polymorphic selectors
            if len(cards) == 0:
                cards = page.query_selector_all(
                    'div[class*="DealCard"], '
                    'div[class*="deal-card"], '
                    'div[class*="dealCard"]'
                )
                print(f"[EXTRACT] Strategy 3 (polymorphic classes): {len(cards)} data points localized")

            # Selector Strategy 4: Anchor-based deep link extraction
            if len(cards) == 0:
                cards = page.query_selector_all(
                    'div.a-section a[href*="/dp/"], '
                    'div.a-section a[href*="/deal/"], '
                    'div.a-cardui'
                )
                print(f"[EXTRACT] Strategy 4 (anchor deep links): {len(cards)} data points localized")

            print(f"[EXTRACT] Total data points localized: {len(cards)}")

            for i, card in enumerate(cards):
                try:
                    card_text = card.inner_text()

                    # Compute variance coefficient from raw text
                    porcentagem = extract_variance_coefficient(card_text)

                    if porcentagem <= VARIANCE_THRESHOLD:
                        continue

                    # Extract product label from DOM subtree
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
                        linhas = [l.strip() for l in card_text.split("\n") if len(l.strip()) > 10]
                        titulo = linhas[0] if linhas else f"DataPoint #{i+1}"

                    # Extract reference URI from anchor elements
                    link_el = card.query_selector('a[href*="/dp/"], a[href*="/deal/"], a[href]')
                    link = ""
                    data_hash = f"dp_{i}_{porcentagem}"
                    if link_el:
                        href = link_el.get_attribute("href")
                        if href:
                            if href.startswith("/"):
                                href = f"https://www.amazon.com.br{href}"
                            link = href
                            asin_match = re.search(r"/dp/([A-Z0-9]{10})", href)
                            deal_match = re.search(r"dealid=([^&]+)", href, re.IGNORECASE)
                            if asin_match:
                                data_hash = asin_match.group(1)
                            elif deal_match:
                                data_hash = deal_match.group(1)

                    # Extract current price tensor from DOM
                    preco_el = card.query_selector(
                        'span.a-price span.a-offscreen, '
                        'span.a-price-whole, '
                        'span[class*="price"]'
                    )
                    preco = preco_el.inner_text().strip() if preco_el else ""
                    if not preco:
                        preco_match = re.search(r"R\$\s*[\d.,]+", card_text)
                        preco = preco_match.group(0) if preco_match else "N/A"

                    # PRIORIDADE 1: Extract list price from strikethrough (.a-price.a-text-price)
                    preco_antigo_el = card.query_selector(
                        'span.a-price.a-text-price span.a-offscreen'
                    )
                    preco_antigo = preco_antigo_el.inner_text().strip() if preco_antigo_el else ""
                    
                    # DEFINITIVE sanitization: remove ALL text artifacts + strict 2 decimal places
                    def sanitize_price_definitive(p):
                        if not p or p == "N/A":
                            return p
                        # Remove text artifacts like 'PreçodaOferta' and other glued text
                        p_clean = re.sub(r"[A-Za-z]+", "", p)
                        # Remove EVERYTHING except numbers and comma
                        p_clean = re.sub(r"[^0-9,]", "", p_clean)
                        # Remove multiple commas, keep only the first (decimal separator)
                        parts = p_clean.split(",")
                        if len(parts) > 2:
                            p_clean = parts[0] + "," + "".join(parts[1:])
                        # Ensure format: digits,optional comma,digits
                        p_clean = re.sub(r",+", ",", p_clean)
                        return p_clean.strip() if p_clean.strip() else "N/A"
                    
                    preco_sanitized = sanitize_price_definitive(preco)
                    preco_antigo_sanitized = sanitize_price_definitive(preco_antigo)
                    
                    # Apply strict 2 decimal formatting to current price
                    if preco_sanitized != "N/A":
                        try:
                            preco_num = float(preco_sanitized.replace(",", "."))
                            preco_sanitized = f"{round(preco_num, 2):.2f}".replace(".", ",")
                        except ValueError:
                            pass
                    
                    # PRIORIDADE 2: OBRIGATORY calculation if no old price OR if old price equals current
                    if (not preco_antigo_sanitized or preco_antigo_sanitized == preco_sanitized) and preco_sanitized != "N/A" and porcentagem > 0:
                        try:
                            # Extract numeric value from current price
                            preco_num = float(preco_sanitized.replace(",", "."))
                            # Reverse calculate: old_price = current_price / (1 - discount/100)
                            preco_antigo_calc = preco_num / (1 - porcentagem / 100)
                            # Round to 2 decimal places and format with comma
                            preco_antigo_sanitized = f"{round(preco_antigo_calc, 2):.2f}".replace(".", ",")
                        except (ValueError, ZeroDivisionError):
                            preco_antigo_sanitized = ""

                    # Extract thumbnail URI
                    img_el = card.query_selector("img[src]")
                    img_url = img_el.get_attribute("src") if img_el else ""

                    data_points.append({
                        "id": data_hash,
                        "titulo": titulo,
                        "desconto": porcentagem,
                        "preco": preco_sanitized,
                        "preco_antigo": preco_antigo_sanitized,
                        "link": link,
                        "imagem": img_url,
                    })

                    print(f"  [DATA] {titulo[:60]}... | variance={porcentagem}%")

                except Exception as e:
                    print(f"  [WARN] Failed to parse data point #{i}: {e}")
                    continue

        except Exception as e:
            print(f"[ERROR] Stochastic sampling failed: {e}")
            try:
                page.screenshot(path=debug_path, full_page=True)
                print("[DIAG] Error-state viewport snapshot captured.")
            except Exception:
                pass
        finally:
            browser.close()

    print(f"[RESULT] Data points exceeding {VARIANCE_THRESHOLD}% variance threshold: {len(data_points)}")
    return data_points


def construct_affiliated_uri(link, data_hash):
    """Constructs a normalized URI with affiliation metric parameter."""
    if not link:
        return link
    asin_match = re.search(r"/dp/([A-Z0-9]{10})", link)
    if asin_match:
        clean_uri = f"https://www.amazon.com.br/dp/{asin_match.group(1)}"
    else:
        clean_uri = link.split("?")[0].split("ref=")[0].rstrip("/")
    if AFFILIATION_DATA_METRIC:
        clean_uri = f"{clean_uri}?tag={AFFILIATION_DATA_METRIC}"
    return clean_uri


def ingest_to_primary_endpoint(data_point):
    """Transmits processed data packet to the primary ingestion endpoint."""
    if not INGESTION_ENDPOINT_PRIMARY:
        print("[ERROR] INGESTION_ENDPOINT_PRIMARY not configured. Aborting transmission.")
        return False

    affiliated_uri = construct_affiliated_uri(data_point["link"], data_point["id"])

    # REWRITE: Message assembly with INEGOTIABLE rules
    # 1. Extract and clean product name
    title = data_point['titulo']
    # LIMPEZA DE LIXO: Remove marketing garbage
    title = re.sub(r"Menor preço em \d+ dias", "", title, flags=re.IGNORECASE)
    title = re.sub(r"OFERTA\s*-\s*\d+%\s*off", "", title, flags=re.IGNORECASE)
    title = re.sub(r"R\$\s*Por:", "", title, flags=re.IGNORECASE)
    title = re.sub(r"PreçodaOferta", "", title, flags=re.IGNORECASE)
    title = title.strip()
    # Fallback for empty title
    if not title:
        title = "Produto em Oferta"
    title = title[:200]
    
    # 2. Format prices with round(valor, 2) and comma
    try:
        price_current = float(data_point["preco"].replace(",", "."))
        p_atual = str(round(price_current, 2)).replace('.', ',')
    except (ValueError, AttributeError):
        p_atual = data_point["preco"]
    
    # Get old price
    price_old = data_point.get("preco_antigo", "")
    if price_old and price_old != "N/A":
        try:
            price_old_float = float(price_old.replace(",", "."))
            p_antigo = str(round(price_old_float, 2)).replace('.', ',')
        except (ValueError, AttributeError):
            p_antigo = price_old
    else:
        p_antigo = ""
    
    # 3. SINGLE LINE assembly - NOME DO PRODUTO OBRIGATÓRIO
    discount = data_point['desconto']
    if p_antigo and p_antigo != p_atual and p_antigo != "0,00":
        # COM preço antigo: OFERTA - NOME - DE R$ X por R$ Y (Z% OFF)
        msg = f"📦 **OFERTA - {title} - DE R$ {p_antigo} por R$ {p_atual} ({discount}% OFF) 🔥**"
    else:
        # SEM preço antigo: OFERTA - NOME - R$ X (Z% OFF)
        msg = f"📦 **OFERTA - {title} - R$ {p_atual} ({discount}% OFF) 🔥**"
    
    # 4. Add link on separate line
    mensagem = f"{msg}\n{affiliated_uri}"

    payload = {"content": mensagem}

    try:
        response = requests.post(
            INGESTION_ENDPOINT_PRIMARY,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        if response.status_code == 204:
            print("[INGEST] Data packet successfully transmitted to primary endpoint.")
            return True
        else:
            print(f"[INGEST_ERROR] Endpoint returned HTTP {response.status_code}: {response.text}")
            return False
    except requests.RequestException as e:
        print(f"[INGEST_ERROR] Connection to primary endpoint failed: {e}")
        return False


def main():
    """Main execution pipeline for the Market Regressor Engine."""
    print("=" * 60)
    print("[INIT] Market Regressor Engine — Stochastic Analysis Pipeline v2.1")
    print("=" * 60)

    # Validate runtime configuration
    if not INGESTION_ENDPOINT_PRIMARY:
        print("[FATAL] INGESTION_ENDPOINT_PRIMARY not defined. Pipeline aborted.")
        return
    if not AFFILIATION_DATA_METRIC:
        print("[WARN] AFFILIATION_DATA_METRIC not defined. URIs will lack affiliation parameter.")

    # Execute stochastic price sampling
    data_points = execute_stochastic_sampling()

    if not data_points:
        print("[RESULT] No data points exceeded variance threshold. Pipeline complete.")
        return

    # Sort by variance coefficient (descending) and select optimal data point
    data_points.sort(key=lambda x: x["desconto"], reverse=True)
    optimal_point = data_points[0]

    print(f"\n[OPTIMAL] Highest variance data point identified:")
    print(f"   Label: {optimal_point['titulo'][:80]}")
    print(f"   Variance: {optimal_point['desconto']}%")
    print(f"   Price tensor: {optimal_point['preco']}")

    # Check against processed metadata store for deduplication
    processed_hashes = load_processed_hashes()
    if optimal_point["id"] in processed_hashes:
        print(f"\n[DEDUP] Data hash already exists in metadata store (hash: {optimal_point['id']}). Scanning alternatives...")
        alternative = None
        for dp in data_points:
            if dp["id"] not in processed_hashes:
                alternative = dp
                break

        if not alternative:
            print("[DEDUP] All data points already processed. Pipeline complete.")
            return

        optimal_point = alternative
        print(f"\n[DEDUP] Alternative data point selected:")
        print(f"   Label: {optimal_point['titulo'][:80]}")
        print(f"   Variance: {optimal_point['desconto']}%")

    # Transmit to primary ingestion endpoint
    success = ingest_to_primary_endpoint(optimal_point)

    if success:
        persist_data_hash(optimal_point["id"])
        synchronize_version_control()

    print("\n" + "=" * 60)
    print("[DONE] Pipeline execution complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
