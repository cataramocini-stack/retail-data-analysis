# 📊 Predictive Retail Engine & Macro-Trend Analysis

## 📈 Overview
Este repositório contém uma estrutura avançada de **Engenharia de Dados** voltada para a captura e análise volumétrica de indicadores de preços no varejo digital brasileiro. O motor utiliza técnicas de **Headless Automation** para monitorar flutuações de mercado em tempo real, permitindo a identificação de anomalias estatísticas em catálogos de larga escala.

## 🧠 Core Objectives
* **Análise de Volatilidade**: Monitoramento de *Price Drops* superiores a 2 sigma (desvio padrão) da média de mercado.
* **Filtro de Relevância**: Algoritmo de priorização baseado em margem de desconto e custo-benefício.
* **Persistence Layer**: Implementação de um sistema de log transacional para evitar colisão de dados e redundância analítica.

## 🛠️ Architecture & Tech Stack
O sistema foi arquitetado para ser resiliente e escalável, utilizando:
* **Python 3.10+**: Core analítico e processamento de strings.
* **Asynchronous Automation Layer**: Para interação de baixo nível com o DOM de plataformas de e-commerce.
* **CI/CD Data Pipeline**: Orquestração via GitHub Actions para processamento distribuído.
* **Data Sink (Webhook)**: Exportação de resultados processados para terminais de visualização (Discord/Slack).

## ⚙️ Statistical Parameters (Environment Variables)
Para garantir a integridade do pipeline, as seguintes métricas devem ser configuradas:
* `TARGET_URL`: Endpoint de destino para o fluxo de dados processados.
* `PARTNER_CODE`: Identificador de rastreabilidade para atribuição de métricas de conversão.

## 📂 Repository Structure
* `analysis_module.py`: O núcleo do motor de decisão estatística.
* `logs.dat`: Database flat-file para controle de estado e idempotência.
* `.github/workflows/`: Orquestrador de jobs temporais.
