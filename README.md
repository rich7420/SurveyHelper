# surveyHelper

A local research companion + **OpenClaw plugin**. Mention a paper in chat and it fetches
it, runs a structured analysis, walks the citation graph, synthesizes what the graph means,
remembers what *you* care about, and proactively surfaces new work — all stored locally.

See [`VISION.md`](VISION.md) for what this is and where it's going, [`ROADMAP.md`](ROADMAP.md)
for status + locked decisions, and the next-arc plan in
[`docs/development-roadmap.md`](docs/development-roadmap.md). Operational detail lives in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`docs/OPERATIONS.md`](docs/OPERATIONS.md).

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

## Quick start (Docker — the whole stack in one command)

```bash
cp .env.example .env          # set ANTHROPIC_API_KEY — the only thing you need
docker compose up -d          # pgvector + worker + MCP server; schema auto-applied
```

The MCP server is then on `http://localhost:8765` (override with `SURVEYHELPER_MCP_PORT`).
Point your agent at it, or install the OpenClaw plugin (see `openclaw/`). No Postgres setup,
no Claude subscription, no machine-specific wiring.

**No API key?** Set `SURVEYHELPER_LLM_BACKEND=cli` to reuse an OpenClaw container's `claude -p`
subscription instead — that path runs natively (below), not in compose.

## Run (native / dev)

```bash
# 1. storage (dedicated pgvector Postgres on :5544)
make db            # or: docker run ... pgvector/pgvector:pg16
make schema        # apply schema.sql

# 2. python env
uv sync

# 3. config
cp .env.example .env   # set ANTHROPIC_API_KEY, or SURVEYHELPER_LLM_BACKEND=cli

# 4. run (dev)
make mcp           # MCP server (streamable-http on :8765)
make worker        # background worker (separate terminal)

# 4b. run (always-on, recommended)
bash deploy/install-services.sh   # launchd services for MCP server + worker

# 5. test
make test
```

## OpenClaw integration

> The MCP server is a **standard MCP endpoint** (`http://localhost:8765/mcp`) usable by **any**
> MCP client (Claude Desktop, other agents). The OpenClaw *ambient recognition* plugin below is an
> optional add-on that injects what the local graph knows about a paper mentioned in chat — with
> no tool call. (Plugin distribution is currently a manual install; ClawHub is planned.)

One command — it auto-detects the OpenClaw container, its CLI version (`mcp add` vs `mcp set`),
and its workspace, then registers the MCP server and installs the skill + heartbeat hook
(idempotent, never clobbers an existing `HEARTBEAT.md`):

```bash
bash openclaw/install.sh           # install
bash openclaw/install.sh --check   # diagnose only
```

A Dockerized OpenClaw reaches the host MCP server via `http://host.docker.internal:8765/mcp`.
The skill ([`openclaw/skills/surveyHelper/SKILL.md`](openclaw/skills/surveyHelper/SKILL.md)) tells
the agent *when* to call `survey`; the heartbeat hook surfaces finished background work.
