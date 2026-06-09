# Contributing to surveyHelper

Thanks for your interest! surveyHelper is a local-first research companion (MCP server + worker +
optional OpenClaw ambient plugin). This guide gets you productive quickly.

## Dev setup

```bash
# storage (pgvector Postgres on :5544) + schema
make db && make schema          # or: docker compose up -d db

# Python env
uv sync                         # installs deps + dev group

# pick an LLM backend (set ONE):
#   export ANTHROPIC_API_KEY=... | OPENAI_API_KEY=... | GEMINI_API_KEY=...
#   or SURVEYHELPER_LLM_BACKEND=cli to reuse an OpenClaw `claude -p` subscription
cp .env.example .env

# run it
make mcp        # MCP server on :8765
make worker     # background worker (separate terminal)
make verify     # first-run self-test (surveys a known paper, prints the card)
```

## Tests

```bash
make test       # uv run pytest -q  (needs Postgres on :5544; DB-less tests still run)
```

CI (`.github/workflows/ci.yml`) spins up pgvector, applies the schema, and runs the full suite on
every push/PR. Please keep it green and add a test with any behavior change.

## Where things live

```
surveyhelper/
  llm/        pluggable backends (anthropic_api / openai_api / gemini_api / claude_cli) + base.py
  db/         thin asyncpg repositories — THE extensibility boundary (papers, jobs, analysis, …)
  sources/    paper APIs (arxiv, s2, github); all egress via http.py + the cross-process limiter
  pipeline/   card · enrich · expand · analyze · synthesize · verify · proactive · deepen
  mcp_server.py · worker.py · scheduler.py · preflight.py · selftest.py
openclaw/     the ambient plugin + skill + heartbeat + installers
```

## Conventions

- **Storage is the boundary.** New persistence goes through a `db/` repository, not raw SQL in
  pipeline code. The DB is the cache.
- **All external HTTP** goes through `http.py` (shared client + retry/backoff + the global rate
  limiter). Don't bypass it.
- **Untrusted paper text** is data, never instructions — keep the system-prompt pinning and the
  no-tools posture in the LLM adapters.
- **Schema is idempotent** (`schema.sql`, all `IF NOT EXISTS`) and applied on boot; add migrations
  the same way so upgrades never break an existing install.
- **Commits**: present-tense, scoped to the change; explain the *why*. Add/adjust a test.
- **The trust invariant**: synthesis asserts only what the grounded + verbatim verifier confirms.
  Don't weaken the verifier to make more claims "pass" — improve the evidence instead.

## Reporting issues

Include: what you ran, the backend (`SURVEYHELPER_LLM_BACKEND`), and the relevant worker/MCP log
lines. The preflight banner at startup prints the resolved config.
