#!/usr/bin/env bash
# Install the surveyHelper plugin into a local (Dockerized) OpenClaw.
#
# Auto-detects: the OpenClaw container, its in-container CLI, its CLI version
# (mcp add vs mcp set), and its workspace dir. Idempotent. Pass --check to only
# run diagnostics.
#
#   bash openclaw/install.sh            # install
#   bash openclaw/install.sh --check    # diagnose only
#
# Env overrides: OPENCLAW_CONTAINER, SURVEYHELPER_MCP_URL
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MCP_URL="${SURVEYHELPER_MCP_URL:-http://host.docker.internal:8765/mcp}"
CHECK_ONLY=false
[[ "${1:-}" == "--check" ]] && CHECK_ONLY=true

step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
ok()   { printf '   \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '   \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '   \033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

# 1. Find the OpenClaw gateway container (publishes 18789, or name contains openclaw)
step "Detecting OpenClaw container"
C="${OPENCLAW_CONTAINER:-}"
if [[ -z "$C" ]]; then
  C="$(docker ps --format '{{.Names}} {{.Ports}}' | awk '/18789/{print $1; exit}')"
  [[ -z "$C" ]] && C="$(docker ps --format '{{.Names}}' | awk '/openclaw/{print; exit}')"
fi
[[ -n "$C" ]] || die "No running OpenClaw container found. Set OPENCLAW_CONTAINER=<name>."
ok "container: $C"

# 2. Determine the in-container CLI command
CLI=""
for cand in "openclaw" "node /app/dist/index.js" "node dist/index.js"; do
  if docker exec "$C" sh -lc "$cand --version" >/dev/null 2>&1; then CLI="$cand"; break; fi
done
[[ -n "$CLI" ]] || die "Could not find the OpenClaw CLI inside $C."
VER="$(docker exec "$C" sh -lc "$CLI --version" 2>/dev/null | grep -oE '[0-9]{4}\.[0-9]+\.[0-9]+' | head -1)"
ok "cli: '$CLI' (OpenClaw ${VER:-unknown})"

# 3. Probe reachability from inside the container
step "Probing MCP server reachability ($MCP_URL)"
code="$(docker exec "$C" sh -lc "curl -s -o /dev/null -w '%{http_code}' -X POST '$MCP_URL' \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2025-06-18\",\"capabilities\":{},\"clientInfo\":{\"name\":\"probe\",\"version\":\"0\"}}}'" 2>/dev/null || echo 000)"
if [[ "$code" == "200" ]]; then ok "reachable (HTTP 200)"; else warn "probe returned HTTP $code — is the MCP server running on :8765?"; fi

# 4. Locate the workspace from the container's mounts
WS_SRC="$(docker inspect "$C" --format '{{range .Mounts}}{{if eq .Destination "/home/node/.openclaw/workspace"}}{{.Source}}{{end}}{{end}}')"
WS="${WS_SRC#/host_mnt}"   # Docker Desktop prefixes host paths with /host_mnt
[[ -n "$WS" && -d "$WS" ]] && ok "workspace: $WS" || warn "workspace mount not found (skill install may be skipped)"

if $CHECK_ONLY; then
  step "Check: configured MCP servers"
  docker exec "$C" sh -lc "$CLI mcp list" 2>&1 | sed 's/^/   /'
  exit 0
fi

# 5. Register the MCP server (mcp add on newer CLIs, mcp set on 2026.5.x)
step "Registering surveyHelper MCP server"
if docker exec "$C" sh -lc "$CLI mcp add surveyHelper --url '$MCP_URL' --transport streamable-http --parallel" >/dev/null 2>&1; then
  ok "registered via 'mcp add'"
elif docker exec "$C" sh -lc "$CLI mcp set surveyHelper '{\"url\":\"$MCP_URL\",\"transport\":\"streamable-http\",\"parallel\":true}'" >/dev/null 2>&1; then
  ok "registered via 'mcp set'"
else
  die "Failed to register the MCP server with both 'mcp add' and 'mcp set'."
fi

# 6. Install skill + heartbeat (additive — never clobber an existing HEARTBEAT.md)
if [[ -n "$WS" && -d "$WS" ]]; then
  step "Installing skill + heartbeat into $WS"
  mkdir -p "$WS/skills/surveyHelper"
  cp "$HERE/skills/surveyHelper/SKILL.md" "$WS/skills/surveyHelper/SKILL.md"
  ok "skills/surveyHelper/SKILL.md"
  HB="$WS/HEARTBEAT.md"
  if grep -q "surveyHelper notifications" "$HB" 2>/dev/null; then
    ok "HEARTBEAT.md already has the surveyHelper section"
  else
    printf '\n' >> "$HB"; cat "$HERE/HEARTBEAT.md" >> "$HB"
    ok "appended surveyHelper section to HEARTBEAT.md"
  fi
fi

# 7. Verify
step "Verifying"
docker exec "$C" sh -lc "$CLI mcp reload" >/dev/null 2>&1 || true   # newer CLIs only
if docker exec "$C" sh -lc "$CLI mcp list" 2>/dev/null | grep -q surveyHelper; then
  ok "surveyHelper is registered"
else
  warn "surveyHelper not shown by 'mcp list' — check manually"
fi
printf '\n\033[1mDone.\033[0m The agent picks up the tools on its next turn.\n'
