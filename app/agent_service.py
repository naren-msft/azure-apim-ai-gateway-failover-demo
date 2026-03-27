"""
Agent Service — Creates and manages the Azure AI Foundry Agent
with a file-search vector store for RAG.

Uses:
  - azure-ai-agents  1.1.0
"""

import logging
from pathlib import Path

from azure.identity import DefaultAzureCredential
from azure.ai.agents import AgentsClient
from azure.ai.agents.models import (
    FileSearchTool,
    FilePurpose,
    VectorStore,
)

from app.config import settings

logger = logging.getLogger(__name__)

_credential = DefaultAzureCredential()


def get_agents_client() -> AgentsClient:
    """Return an authenticated AgentsClient pointing at the Foundry project."""
    return AgentsClient(
        endpoint=settings.AGENT_ENDPOINT,
        credential=_credential,
    )


def create_vector_store(agents: AgentsClient, display_name: str = "contoso-docs") -> VectorStore:
    """Upload sample docs and create a vector store."""
    sample_dir = Path(__file__).parent / "sample_docs"
    file_ids: list[str] = []

    for doc_path in sorted(sample_dir.glob("*.md")):
        logger.info("Uploading %s …", doc_path.name)
        uploaded = agents.files.upload_and_poll(
            file_path=str(doc_path),
            purpose=FilePurpose.AGENTS,
        )
        file_ids.append(uploaded.id)
        logger.info("  → file id: %s", uploaded.id)

    logger.info("Creating vector store '%s' with %d files …", display_name, len(file_ids))
    vector_store = agents.vector_stores.create_and_poll(
        file_ids=file_ids,
        name=display_name,
    )
    logger.info("Vector store created: %s (status=%s)", vector_store.id, vector_store.status)
    return vector_store


def create_agent(agents: AgentsClient, vector_store_id: str) -> str:
    """
    Create a Foundry Agent with file-search tool backed by the vector store.
    Returns the agent ID.
    """
    file_search = FileSearchTool(vector_store_ids=[vector_store_id])

    agent = agents.create_agent(
        model="gpt-4.1",
        name="Contoso Assistant",
        instructions=(
            "You are the Contoso Electronics assistant. "
            "Answer user questions using the documents in your vector store. "
            "Be concise, helpful, and cite specific product names or policy details when relevant. "
            "If the answer is not in the documents, say so honestly."
        ),
        tools=file_search.definitions,
        tool_resources=file_search.resources,
    )
    logger.info("Agent created: %s", agent.id)
    return agent.id


def run_agent_turn(agents: AgentsClient, agent_id: str, thread_id: str | None, user_message: str) -> dict:
    """
    Send a user message to the agent and return the response.

    Returns:
        {
            "response": str,
            "thread_id": str,
            "region": str | None,
            "failover": bool,
        }
    """
    # Create or reuse thread
    if thread_id:
        thread = agents.threads.get(thread_id)
    else:
        thread = agents.threads.create()

    # Add user message
    agents.messages.create(
        thread_id=thread.id,
        role="user",
        content=user_message,
    )

    # Run the agent and wait for completion
    run = agents.runs.create_and_process(
        thread_id=thread.id,
        agent_id=agent_id,
    )

    if run.status == "failed":
        error_msg = run.last_error.message if run.last_error else "Unknown error"
        logger.error("Agent run failed: %s", error_msg)
        return {
            "response": f"Agent error: {error_msg}",
            "thread_id": thread.id,
            "region": None,
            "failover": False,
        }

    # Get the latest assistant message
    messages = agents.messages.list(thread_id=thread.id)
    assistant_messages = [m for m in messages if m.role == "assistant"]

    response_text = ""
    if assistant_messages:
        latest = assistant_messages[0]
        for block in latest.content:
            if hasattr(block, "text"):
                response_text += block.text.value

    # Region info from run metadata (if APIM headers are propagated)
    region = None
    failover = False
    if hasattr(run, "metadata") and run.metadata:
        region = run.metadata.get("x-backend-region")

    return {
        "response": response_text or "(No response from agent)",
        "thread_id": thread.id,
        "region": region,
        "failover": failover,
    }
