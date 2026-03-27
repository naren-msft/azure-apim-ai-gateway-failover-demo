# Azure APIM AI Gateway + Foundry Agent Demo

> Demonstrates Azure API Management AI Gateway load-balancing and 429 failover
> across two Azure OpenAI (GPT-4.1) deployments in East US 2 and Sweden Central,
> with an AI Agent built on the latest Azure AI Foundry SDK.

## 🎬 Demo

<p align="center">
  <img src="https://raw.githubusercontent.com/naren-msft/azure-apim-ai-gateway-failover-demo/master/assets/demo.gif" alt="Azure APIM AI Gateway Failover Demo" width="100%">
</p>

## Architecture

```
User ──► FastAPI ──► Azure APIM (AI Gateway)
                      ┌────────┴────────┐
                      ▼                  ▼
               Azure OpenAI        Azure OpenAI
               (East US 2)        (Sweden Central)
               GPT-4.1             GPT-4.1

         ──► AI Foundry Agent (RAG mode with vector store)
```

**How it works:**
- APIM sits between the Foundry Agent and two regional Azure OpenAI backends
- A **backend pool** load-balances requests 50/50 across both regions
- When a backend returns **HTTP 429** (rate-limited), APIM's **circuit breaker** trips and routes traffic to the healthy backend
- The chat UI shows which region served each response via a region badge
- The `simulate_load.py` script generates enough traffic to trigger 429s and demonstrate live failover

## Prerequisites

| Tool | Version |
|------|---------|
| [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) | ≥ 2.60 |
| [Bicep CLI](https://learn.microsoft.com/azure/azure-resource-manager/bicep/install) | ≥ 0.28 |
| [Python](https://www.python.org/downloads/) | ≥ 3.11 |
| Azure subscription with **Azure OpenAI** access in East US 2 & West US 2 | — |

## Quick Start

### 1. Clone & set up the virtual environment

```powershell
cd C:\Users\namirineni\source\apim-ai-gateway-demo

# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### 2. Deploy Azure infrastructure

```powershell
# Log in to Azure
az login

# Deploy (takes ~15-30 min — APIM provisioning is slow)
.\scripts\deploy.ps1 -ResourceGroup rg-apim-ai-demo -Location eastus2
```

This creates:
- 2× Azure OpenAI accounts with GPT-4o deployments (East US 2 & West US 2)
- 1× Azure API Management with AI Gateway backend pool + 429 failover policies
- 1× Azure AI Foundry Hub + Project with APIM connection
- 1× Storage Account (required by AI Hub)

A `.env` file is auto-generated with the connection details.

### 3. Create the AI Agent & Vector Store

```powershell
python scripts/setup_agent.py
```

This uploads sample documents (product FAQ, company policies) into a Foundry-managed
vector store and creates an agent with the file-search tool. The `AGENT_ID` is
automatically written to `.env`.

### 4. Run the app

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

### 5. Demo the failover

In a second terminal:

```powershell
cd C:\Users\namirineni\source\apim-ai-gateway-demo
.\.venv\Scripts\Activate.ps1

# Send 50 concurrent requests to trigger 429s
python scripts/simulate_load.py --requests 50 --concurrency 10
```

Watch the chat UI's status bar — you'll see requests shift between regions as
429 rate-limits trigger the circuit breaker.

## Project Structure

```
apim-ai-gateway-demo/
├── infra/                          # Bicep IaC templates
│   ├── main.bicep                  # Orchestrator
│   ├── main.bicepparam             # Default parameters
│   └── modules/
│       ├── openai.bicep            # Azure OpenAI + GPT-4o
│       ├── apim.bicep              # APIM AI Gateway + policies
│       ├── ai-hub.bicep            # AI Foundry Hub + Project
│       └── storage.bicep           # Storage account
├── app/                            # Python application
│   ├── main.py                     # FastAPI entry point
│   ├── agent_service.py            # Agent + vector store logic
│   ├── config.py                   # Environment config
│   ├── static/index.html           # Chat UI
│   └── sample_docs/                # Documents for RAG
├── scripts/
│   ├── deploy.ps1                  # Infra deployment
│   ├── setup_agent.py              # One-time agent setup
│   └── simulate_load.py            # Load generator for 429 demo
├── requirements.txt
├── .env.example
└── .gitignore
```

## Key APIM Policies

The APIM module (`infra/modules/apim.bicep`) configures:

1. **Backend Pool** — Round-robin (50/50 weight) across East US 2 and West US 2
2. **Circuit Breaker** — Trips on a single 429 response, holds for 10 seconds, respects `Retry-After` headers
3. **Dynamic API Key** — Sets the correct `api-key` header based on which backend was selected
4. **Region Header** — Adds `x-backend-region` response header so the UI can display which region served the request

## SDK Versions

| Package | Version |
|---------|---------|
| `azure-ai-projects` | 2.0.1 |
| `azure-ai-agents` | 1.1.0 |
| `azure-identity` | 1.21.0 |
| `fastapi` | 0.115.12 |

## Troubleshooting

| Issue | Solution |
|-------|----------|
| APIM deployment times out | APIM Developer SKU takes 15-30 min. Check `az deployment group show`. |
| `AGENT_ID not configured` | Run `python scripts/setup_agent.py` and check `.env`. |
| No 429s during load test | Increase `--requests` or `--concurrency`, or lower the TPM quota in the OpenAI deployment. |
| `cryptography` build fails | Use `pip install --only-binary=:all: cryptography` before installing requirements. |

## License

This demo is provided as-is for educational purposes.
