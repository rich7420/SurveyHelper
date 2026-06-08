#!/usr/bin/env bash
# Install + load the surveyHelper launchd services (MCP server + worker).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LA="$HOME/Library/LaunchAgents"
mkdir -p "$LA" "$HOME/SurveyHelper/logs"

for svc in com.surveyhelper.mcp com.surveyhelper.worker; do
  cp "$HERE/launchd/$svc.plist" "$LA/$svc.plist"
  launchctl bootout "gui/$(id -u)/$svc" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$LA/$svc.plist"
  launchctl enable "gui/$(id -u)/$svc"
  echo "loaded $svc"
done

echo
echo "Status:"
launchctl list | grep surveyhelper || echo "(none yet — check logs in ./logs/)"
