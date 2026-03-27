"""
Configuration module — reads .env and exposes settings.
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # Azure AI Foundry Agent endpoint
    # Format: https://<aiservices-id>.services.ai.azure.com/api/projects/<project-name>
    AGENT_ENDPOINT: str = os.environ.get("AGENT_ENDPOINT", "")

    # Pre-created agent ID (set after running scripts/setup_agent.py)
    AGENT_ID: str = os.environ.get("AGENT_ID", "")

    # APIM gateway URL (used by simulate_load.py)
    APIM_GATEWAY_URL: str = os.environ.get("APIM_GATEWAY_URL", "")
    APIM_SUBSCRIPTION_KEY: str = os.environ.get("APIM_SUBSCRIPTION_KEY", "")


settings = Settings()
