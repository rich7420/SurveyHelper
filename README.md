# surveyHelper

A local research companion + **OpenClaw plugin**. Mention a paper in chat and it fetches
it, runs a structured analysis, walks the citation graph, synthesizes what the graph means,
remembers what *you* care about, and proactively surfaces new work — all stored locally.

See [`plan.md`](plan.md) for the full design and [`DECISIONS.md`](DECISIONS.md) for the
locked decisions (these supersede the plan where they disagree).

## Architecture (plan §3)

Three components, one division of labor:

- **MCP server** (`surveyhelper.mcp_server`) — the front door OpenClaw calls. Returns the
  instant **card** synchronously and enqueues deep work.
- **Worker** (`surveyhelper.worker`) — background daemon, owns paced execution. Drains
  `research_jobs` (`FOR UPDATE SKIP LOCKED`). Independent of whether OpenClaw is up.
- **Postgres + pgvector** — the memory: paper graph, analyses, personal layer.

```
surveyhelper/
  config.py  models.py  logging_setup.py  ratelimit.py  http.py
  db/        __init__(pool)  papers  analysis  jobs  notifications
  sources/   identifiers  arxiv  s2  github      (all egress via http.py + global limiter)
  pipeline/  resolve.py (step 0)  card.py (steps 0/1/3/7, no LLM)
  worker.py  mcp_server.py
```

### The instant card (Phase 0-1, no LLM)
- **Step 0** resolve id → canonical paper (arXiv-only on the sync path → ~1-2s)
- **Step 1** purpose/pain point — ladder: S2 `tldr` → abstract first sentences → none
- **Step 3** backward references → citation-graph edges
- **Step 7** code — GitHub URL in abstract → verify repo

The sync card never blocks on S2's throttled pool. A background **`enrich`** job then
fills the S2 `tldr` (upgrading step 1) and references (step 3), deferring with capped
exponential backoff if S2 is throttled (`research_jobs.run_after`/`attempts`). Deep
grounded steps (2/4/5/6 via PaperQA2) are Phase 2.

### MCP tools
`survey` · `get_paper` · `get_graph` · `job_status` · `pending_notifications`

## Run

```bash
# 1. storage (dedicated pgvector Postgres on :5544)
make db            # or: docker run ... pgvector/pgvector:pg16
make schema        # apply schema.sql

# 2. python env
uv sync

# 3. config
cp .env.example .env   # Phase 0-1 needs no keys (GitHub token optional)

# 4. run (dev)
make mcp           # MCP server (streamable-http on :8765)
make worker        # background worker (separate terminal)

# 4b. run (always-on, recommended)
bash deploy/install-services.sh   # launchd services for MCP server + worker

# 5. test
make test
```

## OpenClaw integration

Register the MCP server (HTTP) in `~/.openclaw/openclaw.json`, then add the skill + heartbeat
hook from [`openclaw/`](openclaw/). A Dockerized OpenClaw reaches the host MCP server via
`http://host.docker.internal:8765/mcp`.
