"""
FastAPI application — Chat endpoint backed by Azure AI Foundry Agent
routed through Azure APIM AI Gateway.
"""

import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.config import settings
from app.agent_service import get_agents_client, run_agent_turn

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# In-memory thread store (session_id → thread_id) — demo only
_threads: dict[str, str] = {}

# Agents client (initialised at startup)
_agents_client = None

# Shared httpx client for APIM direct calls
_http_client: httpx.Client | None = None

# System prompt that includes context from our sample docs
SYSTEM_PROMPT = """You are the Contoso Electronics assistant. Use the following product and policy information to answer questions.

PRODUCTS:
- Contoso SmartHub Pro: AI-powered home automation hub, $299.99, 2-year warranty
- Contoso CloudBook 15: 15" laptop, 16GB RAM, 512GB SSD, $899.99
- Contoso WaveLink Earbuds: Noise-cancelling wireless earbuds, 30-hour battery, $149.99
- Contoso VisionBoard 4K: 32" 4K smart display, $599.99
- Contoso PowerCell 20K: 20,000 mAh portable charger, USB-C PD 65W, $49.99

POLICIES:
- 2-year limited warranty on all products; extended plans available
- 30-day returns with original receipt and packaging
- PTO: 20 days/year; Parental Leave: 16 weeks paid
- Remote Work: up to 3 days/week with manager approval
- Enterprise pricing: 10-25% off for orders of 50+ units

Be concise and helpful. Cite specific product names and prices when relevant."""


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _agents_client, _http_client
    _http_client = httpx.Client(timeout=60)

    if settings.AGENT_ENDPOINT:
        logger.info("Initialising Agents client …")
        _agents_client = get_agents_client()
        logger.info("Ready — Agent ID: %s", settings.AGENT_ID)
    else:
        logger.warning("AGENT_ENDPOINT not set — agent mode unavailable")

    if settings.APIM_GATEWAY_URL:
        logger.info("APIM Gateway: %s", settings.APIM_GATEWAY_URL)
    else:
        logger.warning("APIM_GATEWAY_URL not set — direct APIM mode unavailable")

    yield

    if _http_client:
        _http_client.close()
    logger.info("Shutting down")


app = FastAPI(
    title="Azure APIM AI Gateway Demo",
    version="1.0.0",
    lifespan=lifespan,
)

# Serve static files (chat UI)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


# ---- Models ----
class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    mode: str = "apim"  # "apim" (default) or "agent"


class ChatResponse(BaseModel):
    response: str
    thread_id: str = ""
    region: str | None = None
    failover: bool = False
    headers_info: dict | None = None


# ---- Routes ----
@app.get("/")
async def root():
    """Serve the chat UI."""
    return FileResponse("app/static/index.html")


def _raw_apim_call(messages: list[dict], max_tokens: int = 800) -> dict:
    """Low-level APIM call — returns full info including headers for frontend display."""
    url = f"{settings.APIM_GATEWAY_URL}/deployments/gpt-4.1/chat/completions"
    resp = _http_client.post(
        url,
        headers={"api-key": settings.APIM_SUBSCRIPTION_KEY, "Content-Type": "application/json"},
        params={"api-version": "2024-10-21"},
        json={"messages": messages, "max_tokens": max_tokens},
    )
    region = resp.headers.get("x-backend-region", "unknown")

    # Capture interesting response headers
    captured = {}
    for key in ("x-backend-region", "retry-after", "x-ratelimit-remaining-tokens",
                "x-ratelimit-remaining-requests", "apim-request-id", "content-type"):
        val = resp.headers.get(key)
        if val is not None:
            captured[key] = val

    masked_key = f"***{settings.APIM_SUBSCRIPTION_KEY[-4:]}" if settings.APIM_SUBSCRIPTION_KEY else "***"

    pipeline = [
        {"stage": "inbound", "policy": "set-backend-service", "detail": "→ openai-lb-pool"},
        {"stage": "inbound", "policy": "authentication-managed-identity", "detail": "→ Entra ID token added"},
    ]
    if resp.status_code == 429:
        pipeline.append({"stage": "backend", "policy": "forward", "detail": f"→ {region} returned 429"})
        pipeline.append({"stage": "on-error", "policy": "circuit-breaker", "detail": "tripped for 10s"})
    else:
        pipeline.append({"stage": "backend", "policy": "forward", "detail": f"→ {region}"})
        pipeline.append({"stage": "outbound", "policy": "set-header", "detail": f"x-backend-region = {region}"})

    reply = ""
    if resp.status_code == 200:
        data = resp.json()
        reply = data["choices"][0]["message"]["content"]

    return {
        "status": resp.status_code,
        "region": region,
        "reply": reply,
        "headers_info": {
            "request": {
                "method": "POST",
                "url": "/deployments/gpt-4.1/chat/completions?api-version=2024-10-21",
                "headers": {
                    "api-key": masked_key,
                    "Content-Type": "application/json",
                    "Host": "ai-gateway-naren.azure-api.net",
                },
            },
            "response": {"status": resp.status_code, "headers": captured},
            "pipeline": pipeline,
        },
    }


def _chat_via_apim(messages: list[dict]) -> dict:
    """Call APIM gateway directly — raises on non-200."""
    result = _raw_apim_call(messages, max_tokens=800)
    if result["status"] != 200:
        raise HTTPException(status_code=result["status"], detail=f"APIM returned {result['status']}")
    return result


# Simple in-memory conversation history for APIM mode
_apim_histories: dict[str, list[dict]] = {}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Send a message to the agent or APIM and return the response."""

    if req.mode == "agent":
        # --- Agent mode (uses Foundry agent with vector store) ---
        if not settings.AGENT_ID or not _agents_client:
            raise HTTPException(status_code=500, detail="Agent not configured. Run scripts/setup_agent.py first.")
        thread_id = _threads.get(req.session_id)
        try:
            result = run_agent_turn(
                agents=_agents_client,
                agent_id=settings.AGENT_ID,
                thread_id=thread_id,
                user_message=req.message,
            )
        except Exception as e:
            logger.exception("Agent turn failed")
            raise HTTPException(status_code=500, detail=str(e))
        _threads[req.session_id] = result["thread_id"]
        return ChatResponse(
            response=result["response"],
            thread_id=result["thread_id"],
            region=result.get("region"),
            failover=result.get("failover", False),
        )

    else:
        # --- APIM direct mode (shows load balancing per request) ---
        if not settings.APIM_GATEWAY_URL or not settings.APIM_SUBSCRIPTION_KEY:
            raise HTTPException(status_code=500, detail="APIM not configured. Set APIM_GATEWAY_URL and APIM_SUBSCRIPTION_KEY in .env")

        # Build conversation with system prompt
        history = _apim_histories.get(req.session_id, [])
        if not history:
            history = [{"role": "system", "content": SYSTEM_PROMPT}]
        history.append({"role": "user", "content": req.message})

        try:
            result = _chat_via_apim(history)
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("APIM call failed")
            raise HTTPException(status_code=500, detail=str(e))

        # Store assistant reply in history
        history.append({"role": "assistant", "content": result["reply"]})
        _apim_histories[req.session_id] = history[-20:]  # Keep last 20 messages

        return ChatResponse(
            response=result["reply"],
            region=result["region"],
            headers_info=result["headers_info"],
        )


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "agent_id": settings.AGENT_ID,
        "apim_url": settings.APIM_GATEWAY_URL,
    }


class LoadTestRequest(BaseModel):
    id: int = 0


LOAD_TEST_PROMPTS = [
    "What products does Contoso Electronics sell?",
    "How much does the SmartHub Pro cost?",
    "What is the Contoso warranty policy?",
    "Does Contoso offer enterprise pricing?",
    "How do I set up the SmartHub Pro?",
    "What payment methods does Contoso accept?",
    "Tell me about the CloudBook 15 laptop.",
    "What is the return policy for Contoso products?",
    "How do I contact Contoso support?",
    "Is there a subscription required for SmartHub?",
    "What are the WaveLink Earbuds features?",
    "Describe the VisionBoard 4K display.",
    "What is the PowerCell 20K battery capacity?",
    "Does Contoso have a sustainability program?",
    "What is the Contoso remote work policy?",
]


@app.post("/load-test-proxy")
async def load_test_proxy(req: LoadTestRequest):
    """Proxy a single load-test request through APIM and return status + region + prompt + headers."""
    if not settings.APIM_GATEWAY_URL or not settings.APIM_SUBSCRIPTION_KEY:
        raise HTTPException(status_code=500, detail="APIM not configured")

    prompt = LOAD_TEST_PROMPTS[req.id % len(LOAD_TEST_PROMPTS)]
    try:
        result = _raw_apim_call(
            [
                {"role": "system", "content": "You are a helpful Contoso Electronics assistant. Reply concisely in 1-2 sentences."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=80,
        )
        return {
            "status": result["status"],
            "region": result["region"],
            "id": req.id,
            "prompt": prompt,
            "answer": result["reply"],
            "headers_info": result["headers_info"],
        }
    except Exception as e:
        return {"status": 0, "region": "error", "id": req.id, "prompt": prompt, "answer": "", "headers_info": None, "error": str(e)}
