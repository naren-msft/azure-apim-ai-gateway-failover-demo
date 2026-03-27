"""
setup_agent.py — One-time setup to create the Foundry Agent + Vector Store.

Usage:
    cd apim-ai-gateway-demo
    .\.venv\Scripts\Activate.ps1
    python scripts/setup_agent.py

After running, this script prints the AGENT_ID. Copy it into your .env file.
"""

import logging
import sys
import os

# Ensure the project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.agent_service import get_agents_client, create_vector_store, create_agent

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def main():
    if not settings.AGENT_ENDPOINT:
        print("❌ AGENT_ENDPOINT not set in .env")
        print("   Run scripts/deploy.ps1 first, or set it manually.")
        sys.exit(1)

    print("=" * 60)
    print("  Azure AI Foundry Agent + Vector Store Setup")
    print("=" * 60)

    # 1. Get agents client
    print("\n[1/3] Connecting to AI Foundry project …")
    agents = get_agents_client()

    # 2. Create vector store with sample docs
    print("\n[2/3] Creating vector store with sample documents …")
    vector_store = create_vector_store(agents, display_name="contoso-docs")
    print(f"  ✅ Vector store ID: {vector_store.id}")

    # 3. Create the agent
    print("\n[3/3] Creating agent with file-search tool …")
    agent_id = create_agent(agents, vector_store_id=vector_store.id)
    print(f"  ✅ Agent ID: {agent_id}")

    # 4. Update .env with agent ID
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            content = f.read()
        content = content.replace("AGENT_ID=", f"AGENT_ID={agent_id}", 1)
        with open(env_path, "w") as f:
            f.write(content)
        print(f"\n  ✅ Updated .env with AGENT_ID={agent_id}")
    else:
        print(f"\n  ⚠️  No .env file found. Add this to your .env:")
        print(f"      AGENT_ID={agent_id}")

    print("\n" + "=" * 60)
    print("  Setup complete! Start the app with:")
    print("    uvicorn app.main:app --reload")
    print("=" * 60)


if __name__ == "__main__":
    main()
