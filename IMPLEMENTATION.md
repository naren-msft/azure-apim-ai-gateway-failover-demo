# Azure APIM AI Gateway — Full Implementation Guide

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Azure Resources](#azure-resources)
4. [APIM Gateway Configuration](#apim-gateway-configuration)
5. [AI Foundry Agent Setup](#ai-foundry-agent-setup)
6. [Application Code](#application-code)
7. [Frontend Dashboard](#frontend-dashboard)
8. [How to Run](#how-to-run)
9. [Demonstrating 429 Failover](#demonstrating-429-failover)
10. [Troubleshooting](#troubleshooting)

---

## Overview

This project is a full end-to-end demo of **Azure API Management (APIM) AI Gateway** with **Microsoft AI Foundry**, showcasing:

- **Load-balanced routing** across two Azure OpenAI deployments in different regions
- **Automatic 429 failover** via APIM circuit breakers — when one region is rate-limited, traffic seamlessly shifts to the other
- **AI Foundry Agent** with vector store (RAG) for intelligent Q&A
- **Live visual dashboard** showing policy execution, headers, pipeline stages, architecture animations, and region distribution in real time

### Key Technologies

| Component | Technology |
|-----------|-----------|
| Gateway | Azure API Management (BasicV2) |
| AI Models | Azure OpenAI GPT-4.1 (two regions) |
| Agent Framework | Azure AI Foundry SDK (`azure-ai-agents==1.1.0`) |
| Backend | Python FastAPI + Uvicorn |
| Frontend | Single-page HTML/CSS/JS (no framework) |
| Auth | Entra ID Managed Identity (APIM → OpenAI) |
| IaC | Bicep templates (optional) |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        User (Browser)                            │
│                     http://localhost:8000                         │
└─────────────────────────┬────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────────┐
│                    FastAPI Application                            │
│                                                                  │
│   /chat (APIM mode)  ──► APIM Gateway ──► OpenAI backends       │
│   /chat (Agent mode) ──► AI Foundry Agent (internal routing)     │
│   /load-test-proxy   ──► APIM Gateway (15 varied prompts)       │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│           Azure APIM: ai-gateway-naren (East US)                 │
│                                                                  │
│   ┌─────────────────────────────────────────────────────┐        │
│   │  Inbound Policy                                     │        │
│   │    1. set-backend-service → openai-lb-pool          │        │
│   │    2. authentication-managed-identity → Entra ID    │        │
│   └─────────────────────────────────────────────────────┘        │
│                           │                                      │
│                    ┌──────┴──────┐                                │
│                    ▼             ▼                                │
│   ┌────────────────────┐ ┌────────────────────┐                  │
│   │ openai-eastus2     │ │ openai-swedencentral│                 │
│   │ Weight: 50, Pri: 1 │ │ Weight: 50, Pri: 1  │                 │
│   │ Circuit Breaker:   │ │ Circuit Breaker:    │                 │
│   │  Trip: 1×429/10s   │ │  Trip: 1×429/10s    │                 │
│   │  Hold: 10s         │ │  Hold: 10s          │                 │
│   └────────┬───────────┘ └────────┬────────────┘                 │
│            │                      │                              │
│   ┌────────┴──────────────────────┴────────────┐                 │
│   │  Outbound Policy                           │                 │
│   │    set-header: x-backend-region            │                 │
│   └────────────────────────────────────────────┘                 │
└──────────────────────────────────────────────────────────────────┘
                    │                      │
                    ▼                      ▼
┌─────────────────────────┐  ┌─────────────────────────┐
│  Azure OpenAI           │  │  Azure OpenAI           │
│  East US 2              │  │  Sweden Central         │
│  demo-aifoundry-resource│  │  nextgen-ai-1-resource  │
│  Model: GPT-4.1         │  │  Model: GPT-4.1         │
└─────────────────────────┘  └─────────────────────────┘
```

### Dual-Mode Design

The application supports two modes:

1. **APIM Gateway Mode** (default) — Calls APIM directly, showing load balancing and region per request. Includes embedded Contoso product/policy context as a system prompt.

2. **Foundry Agent Mode** — Uses the AI Foundry Agent with vector store RAG. Routes through Foundry's internal model connection (not APIM), so no region visibility. Better for demonstrating RAG capabilities.

The load test always uses APIM mode to demonstrate failover visually.

---

## Azure Resources

All resources are in **subscription `MCAPS-narendraamirineni`** (`7b891a84-e04b-4485-8ed5-abaeb25735e6`), resource group **`nextgen-ai-rg`**.

### Resource Inventory

| Resource | Type | Region | Purpose |
|----------|------|--------|---------|
| `ai-gateway-naren` | APIM (BasicV2) | East US | AI Gateway with load balancing |
| `demo-aifoundry-resource` | Azure OpenAI | East US 2 | Primary GPT-4.1 deployment |
| `nextgen-ai-1-resource` | Azure OpenAI | Sweden Central | Secondary GPT-4.1 deployment |
| `demo-aifoundry-resource` | AI Services | East US 2 | AI Foundry project host |

### Authentication

Both OpenAI resources have **`disableLocalAuth=true`** — API keys are disabled, Entra ID authentication only.

APIM's **system-assigned managed identity** (principal: `56ea9fe9-8cf7-4780-8f6f-00d974b8b494`) has the **"Cognitive Services OpenAI User"** role on both OpenAI resources, enabling it to authenticate via the `authentication-managed-identity` policy.

---

## APIM Gateway Configuration

### API Definition

| Property | Value |
|----------|-------|
| Name | `azure-openai-lb` |
| Path | `/openai` |
| Subscription Required | Yes (header: `api-key`) |
| Subscription Name | `AI Gateway Demo Sub` (`ai-gw-demo-sub`) |

**Operation:**
- `POST /deployments/{deployment-id}/chat/completions` — Chat completions endpoint

### Backends

Two backends pointing to Azure OpenAI resources in different regions:

#### openai-eastus2
```
URL:       https://demo-aifoundry-resource.openai.azure.com
Protocol:  HTTP
Auth:      Managed Identity → Cognitive Services OpenAI User
```

#### openai-swedencentral
```
URL:       https://nextgen-ai-1-resource.openai.azure.com
Protocol:  HTTP
Auth:      Managed Identity → Cognitive Services OpenAI User
```

### Circuit Breaker (per backend)

```json
{
  "rules": [{
    "name": "openAIBreakerRule",
    "tripDuration": "PT10S",
    "acceptRetryAfter": true,
    "tripCondition": {
      "consecutiveStatusCodeRanges": ["429"],
      "count": 1,
      "intervalInSeconds": 10
    },
    "retryCondition": {
      "consecutiveStatusCodeRanges": ["200"],
      "count": 1,
      "intervalInSeconds": 10
    }
  }]
}
```

**Behavior:** After just 1 HTTP 429 response, the circuit **trips** for 10 seconds. During this time, APIM stops sending traffic to that backend. After 10 seconds, it probes with one request — if the probe gets 200, the circuit **closes** and traffic resumes.

### Backend Pool

```
Pool: openai-lb-pool
├── openai-eastus2       (weight: 50, priority: 1)
└── openai-swedencentral (weight: 50, priority: 1)

Load Balancing: Weighted Round-Robin (50/50 split)
```

### Full Policy XML

```xml
<policies>
    <inbound>
        <base />
        <!-- Route to load-balanced backend pool -->
        <set-backend-service backend-id="openai-lb-pool" />
        <!-- Authenticate with Entra ID managed identity -->
        <authentication-managed-identity
            resource="https://cognitiveservices.azure.com" />
    </inbound>

    <backend>
        <base />
    </backend>

    <outbound>
        <base />
        <!-- Add response header showing which region served the request -->
        <set-header name="x-backend-region" exists-action="override">
            <value>@{
                var url = context.Request.Url.ToString();
                if (url.Contains("demo-aifoundry-resource")) {
                    return "eastus2";
                }
                if (url.Contains("nextgen-ai-1-resource")) {
                    return "swedencentral";
                }
                return "unknown";
            }</value>
        </set-header>
    </outbound>

    <on-error>
        <base />
    </on-error>
</policies>
```

**Policy Breakdown:**

| Stage | Policy | Purpose |
|-------|--------|---------|
| Inbound | `set-backend-service` | Routes request to `openai-lb-pool` (weighted 50/50) |
| Inbound | `authentication-managed-identity` | Adds Entra ID bearer token for Cognitive Services |
| Backend | `base` | Forwards to the selected backend from the pool |
| Outbound | `set-header` | Adds `x-backend-region` response header using C# expression |
| On-Error | `base` | Circuit breaker handles 429 errors automatically |

---

## AI Foundry Agent Setup

### Agent Details

| Property | Value |
|----------|-------|
| Agent ID | `asst_lg2NfVlNsWaU1La0GVnv8DuC` |
| Model | `gpt-4.1` |
| Name | `Contoso Assistant` |
| Endpoint | `https://demo-aifoundry-resource.services.ai.azure.com/api/projects/demo-aifoundry` |
| Tools | FileSearchTool (vector store RAG) |

### Vector Store

| Property | Value |
|----------|-------|
| Store ID | `vs_J5nPrJhoPiZuBirLeXXhYOgK` |
| Name | `contoso-docs` |
| Files | `product_faq.md`, `company_policies.md` |

### SDK Usage

The project uses **`azure-ai-agents==1.1.0`** (not the older `azure-ai-projects` connection string approach):

```python
from azure.ai.agents import AgentsClient
from azure.identity import DefaultAzureCredential

# Initialize client
agents = AgentsClient(
    endpoint="https://demo-aifoundry-resource.services.ai.azure.com/api/projects/demo-aifoundry",
    credential=DefaultAzureCredential()
)

# Sub-clients accessed as properties:
agents.files          # Upload files
agents.vector_stores  # Create/manage vector stores
agents.threads        # Create conversation threads
agents.messages       # Send/read messages
agents.runs           # Execute agent runs
```

### Setup Script (`scripts/setup_agent.py`)

Run once to create the agent and vector store:

```powershell
cd apim-ai-gateway-demo
.\.venv\Scripts\Activate.ps1
python scripts/setup_agent.py
```

This script:
1. Uploads `app/sample_docs/*.md` files to AI Foundry
2. Creates a vector store with those files
3. Creates an agent with the `FileSearchTool` pointing to the vector store
4. Writes the `AGENT_ID` to `.env`

---

## Application Code

### Project Structure

```
app/
├── __init__.py
├── config.py           # Settings from .env
├── agent_service.py    # AI Foundry agent client + helpers
├── main.py             # FastAPI app with all endpoints
├── sample_docs/
│   ├── product_faq.md      # Contoso product catalog
│   └── company_policies.md # Contoso HR/return policies
└── static/
    └── index.html      # 3-panel visual dashboard
```

### config.py

Reads environment variables from `.env`:

| Variable | Example |
|----------|---------|
| `AGENT_ENDPOINT` | `https://demo-aifoundry-resource.services.ai.azure.com/api/projects/demo-aifoundry` |
| `AGENT_ID` | `asst_lg2NfVlNsWaU1La0GVnv8DuC` |
| `APIM_GATEWAY_URL` | `https://ai-gateway-naren.azure-api.net/openai` |
| `APIM_SUBSCRIPTION_KEY` | `b924c568...` |

### main.py — Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Serves the dashboard UI |
| `/chat` | POST | Chat with mode selection (`apim` or `agent`) |
| `/load-test-proxy` | POST | Single load-test request through APIM |
| `/health` | GET | Health check |

#### `/chat` — APIM Mode Flow

1. Builds conversation with system prompt (Contoso product/policy context)
2. Calls `_raw_apim_call()` which sends request to APIM
3. Captures request headers (masked API key), response headers (`x-backend-region`, rate limit info)
4. Determines pipeline stages (inbound → backend → outbound or on-error)
5. Returns response + region + `headers_info` for frontend display

#### `/chat` — Agent Mode Flow

1. Gets or creates conversation thread
2. Sends message via `run_agent_turn()`
3. Agent uses vector store to find relevant docs
4. Returns response + thread ID

#### `/load-test-proxy` — Load Test Flow

1. Selects prompt from pool of 15 varied Contoso questions
2. Calls `_raw_apim_call()` with short max_tokens (80)
3. Returns status, region, prompt, answer, and full `headers_info`
4. Does NOT raise on 429 — returns it as data for the dashboard

### agent_service.py — Key Functions

| Function | Purpose |
|----------|---------|
| `get_agents_client()` | Creates authenticated `AgentsClient` |
| `create_vector_store(agents, name)` | Uploads docs + creates vector store |
| `create_agent(agents, vs_id)` | Creates agent with FileSearchTool |
| `run_agent_turn(agents, agent_id, thread_id, msg)` | Executes one conversation turn |

### System Prompt (APIM Mode)

The APIM mode uses an embedded system prompt with Contoso context:

```
Products:
- SmartHub Pro: $299.99, AI home hub, 2-year warranty
- CloudBook 15: $899.99, 15" laptop, 16GB/512GB
- WaveLink Earbuds: $149.99, noise-cancelling, 30hr battery
- VisionBoard 4K: $599.99, 32" smart display
- PowerCell 20K: $49.99, 20000mAh, USB-C PD 65W

Policies:
- 2-year limited warranty, extended plans available
- 30-day returns with receipt
- Enterprise pricing: 10-25% off for 50+ units
```

---

## Frontend Dashboard

The UI is a single HTML file (`app/static/index.html`) with three panels:

### Layout: Chat (25%) | APIM Insights (40%) | Dashboard (35%)

#### Left Panel — Chat
- Text input with Send button
- Mode selector (APIM Gateway / Foundry Agent)
- Region badges on each response
- Typing indicator animation
- Load test button in header

#### Middle Panel — APIM Insights (two tabs)

**Tab 1: ⚡ Live Insights**
- **Policy XML** — syntax-highlighted with live annotations (sections glow blue on success, red on 429)
- **Backend Pool Status** — shows each backend with health dot (green=healthy, red=tripped)
- **Request Pipeline** — animated stage-by-stage visualization (INBOUND → BACKEND → OUTBOUND/ON-ERROR)
- **Live Headers** — real-time request/response headers for the last call

**Tab 2: 📄 Full APIM Config**
- Complete policy XML with comments
- Backend definitions with URLs and circuit breaker rules
- Backend pool configuration with weights and priorities
- Failover behavior explanation
- Subscription details

#### Right Panel — Dashboard
- **Architecture Diagram** — SVG with animated flow lines between User → APIM → Backends (lines dynamically align to nodes via JS)
- **Live Statistics** — total, success, 429s, failovers
- **Region Distribution** — animated bars showing East US 2 vs Sweden Central percentage
- **Event Log** — expandable entries showing prompt, response, status, region per request

### Key Frontend Features

- **Policy animation**: As requests flow, the relevant policy XML sections highlight in sequence
- **Circuit breaker visualization**: Backend dots turn red and show "⚠️ Tripped" on 429
- **Expandable log entries**: Click chevron to see full prompt and response
- **Responsive SVG**: Architecture diagram lines auto-align on load and resize

---

## How to Run

### Prerequisites

- Python 3.11+
- Azure CLI (logged in)
- Azure subscription with existing resources (see [Azure Resources](#azure-resources))

### Setup

```powershell
cd C:\Users\namirineni\source\apim-ai-gateway-demo

# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Copy and fill in environment variables
copy .env.example .env
# Edit .env with your values
```

### Create Agent (one-time)

```powershell
python scripts/setup_agent.py
```

### Start the Server

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open **http://localhost:8000** in your browser.

### Run Load Test (CLI)

```powershell
python scripts/simulate_load.py --requests 50 --concurrency 10
```

Or use the **⚡ Run Load Test** button in the browser UI.

---

## Demonstrating 429 Failover

### Setup for Demo

To reliably trigger 429s, lower the TPM (tokens per minute) on one deployment:

```powershell
# Lower Sweden Central to 1K TPM to trigger rate limits quickly
az cognitiveservices account deployment create `
    --name nextgen-ai-1-resource `
    --resource-group nextgen-ai-rg `
    --deployment-name gpt-4.1 `
    --model-name gpt-4.1 `
    --model-version "2025-04-14" `
    --model-format OpenAI `
    --sku-capacity 1 `
    --sku-name GlobalStandard
```

### Demo Flow

1. Open http://localhost:8000
2. Click **⚡ Run Load Test** — sends 30 requests, concurrency 10
3. Watch the dashboard:
   - Initially requests split ~50/50 between regions
   - Sweden Central hits rate limit → **circuit breaker trips**
   - Backend dot turns **red** → "⚠️ Tripped"
   - Policy `on-error` section glows **red**
   - Architecture diagram shows **red flow line** to Sweden Central
   - All subsequent traffic routes to **East US 2** (green)
   - After 10s, circuit breaker **probes** Sweden Central
   - If probe succeeds → circuit closes, traffic resumes to both

### Restore Capacity After Demo

```powershell
az cognitiveservices account deployment create `
    --name nextgen-ai-1-resource `
    --resource-group nextgen-ai-rg `
    --deployment-name gpt-4.1 `
    --model-name gpt-4.1 `
    --model-version "2025-04-14" `
    --model-format OpenAI `
    --sku-capacity 50 `
    --sku-name GlobalStandard
```

---

## Troubleshooting

### Common Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| `DefaultAzureCredential` fails | Azure CLI not on PATH | Run: `$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")` |
| Agent mode returns 500 | `AGENT_ID` not set | Run `python scripts/setup_agent.py` |
| APIM returns 401 | Subscription key wrong | Check `APIM_SUBSCRIPTION_KEY` in `.env` |
| APIM returns 403 | Managed identity role missing | Grant "Cognitive Services OpenAI User" role to APIM identity on both OpenAI resources |
| No region shown | `x-backend-region` header missing | Verify APIM outbound policy is configured |
| `cryptography` build fails | Win-ARM64 no wheel | Run: `pip install cryptography --only-binary=:all:` before `pip install -r requirements.txt` |
| `aiohttp` build fails | Win-ARM64 no wheel | Use `httpx` instead (already done in this project) |
| Frontend JS not working | Browser cache | Hard refresh: Ctrl+Shift+R |

### Key Notes

- Both OpenAI resources have **local auth disabled** — only Entra ID works. API keys from the Azure portal will NOT work for direct calls.
- The AI Foundry agent routes through Foundry's **internal** model connection, NOT through APIM. That's why we have dual-mode: APIM mode shows gateway behavior, Agent mode shows RAG.
- APIM policy C# expressions must use **block-style** `if(cond){ return x; }` — single-line `if` without braces may fail.
- The `x-backend-region` header is a **custom header** we add in the outbound policy. It's not a built-in Azure header.

---

## File Reference

| File | Lines | Purpose |
|------|-------|---------|
| `app/main.py` | ~240 | FastAPI app, endpoints, APIM call logic |
| `app/agent_service.py` | ~90 | AI Foundry agent client and helpers |
| `app/config.py` | ~20 | Environment variable configuration |
| `app/static/index.html` | ~810 | 3-panel visual dashboard |
| `app/sample_docs/product_faq.md` | ~50 | Contoso product catalog for RAG |
| `app/sample_docs/company_policies.md` | ~60 | Contoso company policies for RAG |
| `scripts/setup_agent.py` | ~60 | One-time agent + vector store creation |
| `scripts/simulate_load.py` | ~100 | CLI load test generator |
| `scripts/deploy.ps1` | ~30 | Bicep infrastructure deployment |
| `infra/main.bicep` | ~60 | Bicep orchestrator |
| `infra/modules/apim.bicep` | ~200 | APIM + backends + policies |
| `infra/modules/openai.bicep` | ~80 | Azure OpenAI deployments |
| `infra/modules/ai-hub.bicep` | ~100 | AI Foundry Hub + Project |
| `infra/modules/storage.bicep` | ~30 | Storage account |
| `requirements.txt` | 8 | Python dependencies |
| `.env.example` | ~12 | Environment template |
| `README.md` | ~120 | Quick-start guide |
