#!/usr/bin/env bash
# Install the surveyHelper ambient-recognition hook plugin into a Dockerized OpenClaw.
# The plugin's before_prompt_build hook calls surveyHelper's /recognize on each turn and
# injects what we know about a mentioned paper — no agent tool call, no LLM in that path.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTAINER="${OPENCLAW_CONTAINER:-generalops-openclaw}"
CLI="${OPENCLAW_CLI:-node /app/dist/index.js}"

echo "==> Copying plugin into $CONTAINER"
docker exec -u root "$CONTAINER" rm -rf /tmp/shp 2>/dev/null || true
docker cp "$HERE/surveyhelper" "$CONTAINER":/tmp/shp
docker exec -u root "$CONTAINER" rm -f /tmp/shp/index.ts || true   # install the compiled entry only

echo "==> Installing"
docker exec "$CONTAINER" sh -lc "$CLI plugins install /tmp/shp"

echo "==> Restarting gateway to load the plugin"
docker restart "$CONTAINER" >/dev/null

echo "Done. Verify:  docker exec $CONTAINER $CLI plugins list | grep -i survey"
echo "Note: for production, add 'surveyhelper' to plugins.allow in openclaw.json (trusted ids)."
