# 📊 Market Regressor Engine

Stochastic price volatility analyzer for the Brazilian e-commerce market index. Performs automated regression analysis on retail pricing data and transmits normalized data packets to a configurable ingestion endpoint.

## ⚙️ Core Capabilities

- 🔬 **Stochastic Price Polling** — Headless chromium-based data collection via Playwright + Stealth
- 📉 **Variance Threshold Filtering** — Isolates data points exceeding configurable volatility coefficient (default: 20%)
- 🏆 **Optimal Data Point Selection** — Ranks by highest variance coefficient
- 🔗 **Affiliation Metric Injection** — Appends configurable affiliation parameter to output URIs
- ✅ **Deduplication Engine** — Cross-references against `processed_metadata.db` persistent store
- 🔄 **Automated Pipeline** — Scheduled execution via GitHub Actions (20-minute polling interval)

## 🚀 Configuration

### 1. Environment Variables

Create a `.env` file in the project root (local development):

```env
INGESTION_ENDPOINT_PRIMARY=https://discord.com/api/webhooks/YOUR_WEBHOOK_HERE
AFFILIATION_DATA_METRIC=your-affiliation-tag
```

### 2. GitHub Secrets

Configure the following **Secrets** in the repository (`Settings > Secrets > Actions`):

| Secret | Description |
|---|---|
| `INGESTION_ENDPOINT_PRIMARY` | Primary data ingestion endpoint URI |
| `AFFILIATION_DATA_METRIC` | Affiliation parameter for URI construction |

### 3. Local Execution

```bash
pip install -r requirements.txt
playwright install chromium
python market_regressor_engine.py
```

## 📂 Project Structure

```
retail-data-analysis/
├── .github/workflows/data_sync.yml    # Market Volatility Analysis Pipeline
├── market_regressor_engine.py          # Stochastic Price Polling Engine
├── processed_metadata.db              # Persistent metadata store
├── requirements.txt                    # Python dependencies
├── .env.example                        # Environment configuration template
├── .gitignore                          # VCS exclusion rules
└── README.md                           # Documentation
```
