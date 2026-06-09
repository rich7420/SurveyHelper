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

# LLM backend (Phase 2). Interchangeable adapters behind surveyhelper.llm.complete:
#   "anthropic" (alias "api") — official Anthropic SDK, ANTHROPIC_API_KEY (default, prompt-cached).
#   "openai"  — official OpenAI SDK, OPENAI_API_KEY.
#   "gemini"  — official google-genai SDK, GEMINI_API_KEY (or GOOGLE_API_KEY).
#   "cli"     — reuse an OpenClaw container's authenticated `claude -p` subscription (no key).
#   "auto"    — first provider whose key is set (anthropic → openai → gemini), else cli.
# Each provider keeps a cheap/high-volume model and a capable model; the pipeline's per-call
# Claude model is mapped to the right tier by the adapter (haiku → summary tier, else main).
LLM_BACKEND = os.environ.get("SURVEYHELPER_LLM_BACKEND", "auto").lower()
LLM_MAX_TOKENS = int(os.environ.get("SURVEYHELPER_LLM_MAX_TOKENS", "8192"))
LLM_CONTAINER = os.environ.get("SURVEYHELPER_OPENCLAW_CONTAINER", "generalops-openclaw")
LLM_MODEL = os.environ.get("SURVEYHELPER_LLM_MODEL", "claude-opus-4-8")            # flagship (synthesis)
LLM_SUMMARY_MODEL = os.environ.get("SURVEYHELPER_LLM_SUMMARY_MODEL", "claude-haiku-4-5")  # high-volume
# Per-provider model tiers (overridable; set these to current IDs for your account).
OPENAI_MODEL = os.environ.get("SURVEYHELPER_OPENAI_MODEL", "gpt-5.5")          # flagship
OPENAI_SUMMARY_MODEL = os.environ.get("SURVEYHELPER_OPENAI_SUMMARY_MODEL", "gpt-5.4-mini")  # no 5.5-mini yet
GEMINI_MODEL = os.environ.get("SURVEYHELPER_GEMINI_MODEL", "gemini-3.5-flash")  # newest GA flagship
GEMINI_SUMMARY_MODEL = os.environ.get("SURVEYHELPER_GEMINI_SUMMARY_MODEL", "gemini-2.5-flash")
# Deep analysis defaults to the cheap model (extraction, high-volume); raise per taste.
ANALYZE_MODEL = os.environ.get("SURVEYHELPER_ANALYZE_MODEL", "claude-haiku-4-5")
# Independent verifier for synthesis contradictions (cross-model from the sonnet synthesizer).
VERIFY_MODEL = os.environ.get("SURVEYHELPER_VERIFY_MODEL", "claude-haiku-4-5")
# Daily LLM spend circuit-breaker (USD). Hitting it pauses LLM work + notifies.
DAILY_BUDGET_USD = float(os.environ.get("SURVEYHELPER_DAILY_BUDGET_USD", "20"))

# Descriptive User-Agent for paper APIs (arXiv best practice).
USER_AGENT = f"surveyHelper/0.1 (+{CONTACT_EMAIL})"
