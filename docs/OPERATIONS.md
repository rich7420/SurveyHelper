# surveyHelper — Operations

Running, monitoring, and troubleshooting the live system.

## Services

| Piece | What | How it runs |
|---|---|---|
| `surveyhelper-pg` | Postgres 16 + pgvector (storage + queue + limiter) | Docker container, port **5544** |
| `com.surveyhelper.mcp` | MCP server (front door) | launchd, **:8765** streamable-http |
| `com.surveyhelper.worker` | background worker | launchd, polls the job queue |
| `generalops-openclaw` | OpenClaw gateway (Claude agent) | Docker, **:18789** |

### Start everything
```bash
# storage
docker start surveyhelper-pg            # or: make db && make schema   (first time)
# services (always-on)
bash deploy/install-services.sh         # loads both launchd agents
# openclaw gateway
docker compose -f ~/generalops-claude-cli/docker-compose.yml up -d
```

### Control the services
```bash
launchctl list | grep surveyhelper                       # status (PID + last exit)
launchctl kickstart -k gui/$(id -u)/com.surveyhelper.mcp     # restart after a code change
launchctl kickstart -k gui/$(id -u)/com.surveyhelper.worker
launchctl bootout gui/$(id -u)/com.surveyhelper.worker       # stop
tail -f logs/worker.log logs/mcp.log                     # logs
```

## Health checks
```bash
# MCP server listening?
lsof -iTCP:8765 -sTCP:LISTEN
# OpenClaw sees the tools?  (generalops uses the 2026.5.7 CLI)
docker exec generalops-openclaw node /app/dist/index.js mcp list
# storage row counts
docker exec surveyhelper-pg psql -U surveyhelper -d surveyhelper -c \
  "SELECT (SELECT count(*) FROM papers) papers, (SELECT count(*) FROM citations) cites,
          (SELECT count(*) FROM research_jobs WHERE status='pending') pending_jobs;"
```

## Troubleshooting

**Cards come back without `tldr`/references (step 1/3 `partial`).**
Semantic Scholar's unauthenticated pool is throttling. The card is intentionally arXiv-only;
the `enrich` job retries with backoff. Fix: set `SEMANTIC_SCHOLAR_API_KEY` in `.env`.

**`enrich` jobs stuck `pending` with a future `run_after`.**
Expected — they're deferred after an S2 throttle (capped exp backoff, ≤8 attempts). Check
`SELECT id,status,attempts,run_after FROM research_jobs WHERE type='enrich';`

**Agent turn returns `401 / FailoverError`.**
The Claude credential expired. The durable fix is documented in memory `generalops-claude-auth`:
the live session reads `~/.claude/.credentials.json` (it ignores `CLAUDE_CODE_OAUTH_TOKEN`), so
synthesize that file from a long-lived `setup-token`. The `generalops-token-refresher` is stopped
on purpose (it would clobber the static credential).

**A survey is slow (~30s).**
A fresh DOI/S2 id (not arXiv) resolves through S2 synchronously and can hit throttling. arXiv ids
are always fast. Title search also needs S2.

## Config
`.env` (see `.env.example`). Phase 0–1 needs no keys; optional: `SEMANTIC_SCHOLAR_API_KEY`,
`GITHUB_TOKEN`, `SURVEYHELPER_CONTACT_EMAIL`. Storage DSN: `SURVEYHELPER_DSN`.
