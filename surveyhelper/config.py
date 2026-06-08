"""Configuration loaded from environment (.env is loaded if present)."""

from __future__ import annotations

import os
from pathlib import Path


def _load_dotenv() -> None:
    """Minimal .env loader (no dependency on python-dotenv)."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        # Real environment variables take precedence over .env.
        os.environ.setdefault(key, val)


_load_dotenv()


DSN: str = os.environ.get(
    "SURVEYHELPER_DSN",
    "postgresql://surveyhelper:surveyhelper@localhost:5544/surveyhelper",
)

SEMANTIC_SCHOLAR_API_KEY = os.environ.get("SEMANTIC_SCHOLAR_API_KEY") or None
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN") or None
OPENALEX_API_KEY = os.environ.get("OPENALEX_API_KEY") or None
UNPAYWALL_EMAIL = os.environ.get("UNPAYWALL_EMAIL") or None
CONTACT_EMAIL = os.environ.get("SURVEYHELPER_CONTACT_EMAIL") or "surveyhelper@localhost"

MCP_HOST = os.environ.get("SURVEYHELPER_MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.environ.get("SURVEYHELPER_MCP_PORT", "8765"))

PIPELINE_VERSION = os.environ.get("SURVEYHELPER_PIPELINE_VERSION", "card-v1")

# Descriptive User-Agent for paper APIs (arXiv best practice).
USER_AGENT = f"surveyHelper/0.1 (+{CONTACT_EMAIL})"
