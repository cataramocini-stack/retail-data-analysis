# 📊 Retail Data Analysis

Bot automatizado que busca as melhores promoções na Amazon Brasil e envia para um Webhook Discord.

## ⚙️ Funcionalidades

- 🔍 Busca ofertas em `amazon.com.br/ofertas` usando **Playwright + Stealth**
- 📉 Filtra apenas itens com **mais de 20% de desconto**
- 🏆 Seleciona a **melhor oferta** (maior desconto)
- 🔗 Adiciona **tag de afiliado** aos links
- ✅ Verifica duplicatas no arquivo `logs.dat`
- 🔄 Execução automática via **GitHub Actions** a cada 20 minutos

## 🚀 Configuração

### 1. Variáveis de Ambiente

Crie um arquivo `.env` na raiz do projeto (para desenvolvimento local):

```env
TARGET_URL=https://discord.com/api/webhooks/SEU_WEBHOOK_AQUI
PARTNER_CODE=sua-tag-de-afiliado
```

### 2. Secrets no GitHub

Configure os seguintes **Secrets** no repositório (`Settings > Secrets > Actions`):

| Secret | Descrição |
|---|---|
| `TARGET_URL` | URL do Webhook Discord |
| `PARTNER_CODE` | Tag de afiliado Amazon |

### 3. Instalação Local

```bash
pip install -r requirements.txt
playwright install chromium
python analysis_module.py
```

## 📂 Estrutura

```
retail-data-analysis/
├── .github/workflows/data_sync.yml   # GitHub Actions (cron 20min)
├── analysis_module.py                 # Script principal
├── logs.dat                           # IDs já enviados
├── requirements.txt                   # Dependências Python
├── .env.example                       # Exemplo de variáveis de ambiente
├── .gitignore                         # Arquivos ignorados pelo Git
└── README.md                          # Documentação
```
