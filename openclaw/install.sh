#!/usr/bin/env bash
# Install the surveyHelper plugin into a local OpenClaw.
#
#   - registers the surveyHelper MCP server (HTTP) with OpenClaw
#   - installs the SKILL.md (when to call survey) and HEARTBEAT.md (notify hook)
#
# Assumes: OpenClaw is running (host or Docker) and the surveyHelper MCP server is
# reachable. For a Dockerized OpenClaw the server is reached via host.docker.internal.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENCLAW_REPO="${OPENCLAW_REPO:-$HOME/openclaw}"          # where docker-compose.yml lives
OPENCLAW_WORKSPACE="${OPENCLAW_WORKSPACE:-$HOME/.openclaw/workspace}"
MCP_URL="${SURVEYHELPER_MCP_URL:-http://host.docker.internal:8765/mcp}"

echo "==> Registering surveyHelper MCP server ($MCP_URL)"
if [[ -f "$OPENCLAW_REPO/docker-compose.yml" ]]; then
  # Dockerized OpenClaw
  docker compose -f "$OPENCLAW_REPO/docker-compose.yml" run --rm openclaw-cli \
    mcp add surveyHelper --url "$MCP_URL" --transport streamable-http --parallel || \
    echo "   (already registered or probe failed — check the server is up)"
else
  # Host-installed OpenClaw
  openclaw mcp add surveyHelper --url "$MCP_URL" --transport streamable-http --parallel || true
fi

echo "==> Installing skill + heartbeat into $OPENCLAW_WORKSPACE"
mkdir -p "$OPENCLAW_WORKSPACE/skills/surveyHelper"
cp "$HERE/skills/surveyHelper/SKILL.md" "$OPENCLAW_WORKSPACE/skills/surveyHelper/SKILL.md"
cp "$HERE/HEARTBEAT.md" "$OPENCLAW_WORKSPACE/HEARTBEAT.md"

echo "==> Reloading MCP config"
if [[ -f "$OPENCLAW_REPO/docker-compose.yml" ]]; then
  docker compose -f "$OPENCLAW_REPO/docker-compose.yml" run --rm openclaw-cli mcp reload || true
fi

echo "Done. Verify with: (in $OPENCLAW_REPO) docker compose run --rm openclaw-cli mcp probe surveyHelper"
