# surveyHelper

**Mention a paper — surveyHelper remembers it, analyzes it, maps its citation graph, and tells you
what the graph *means*. All on your machine, and honest about what it can prove.**

A local-first research companion. It runs as an [MCP](https://modelcontextprotocol.io) server (any
MCP agent can use it) with an optional [OpenClaw](https://github.com/openclaw/openclaw) ambient
plugin. Your papers, analyses, and notes never leave your machine.

## What you get

- **Instant cards** — give it an arXiv id or title and get the paper's purpose, references, and code
  link in seconds.
- **Deep grounded analysis** — contribution, method, results, and limitations, extracted from the
  full text with a faithfulness check.
- **Citation-graph synthesis you can trust** — lineage, open problems, and contradictions across the
  graph. It **only asserts a contradiction when it can quote verbatim evidence from *both* papers**;
  otherwise it labels it *tentative*. It tells you what it can prove and is honest about what it can't.
- **Personal memory** — tracks what *you* care about (interests, papers you've read/understood) and
  proactively surfaces new work.
- **Ambient awareness** — with the OpenClaw plugin, say "the BERT paper" in chat and it injects what
  your graph already knows — no command, no tool call.

## Quick start

You need **Docker** and **one LLM API key** (Anthropic, OpenAI, or Gemini).

```bash
git clone https://github.com/rich7420/SurveyHelper.git && cd SurveyHelper
cp .env.example .env          # set ONE provider key
docker compose up -d          # pgvector + worker + MCP server (:8765) + scheduler
docker compose run --rm worker surveyhelper-verify    # → "✓ surveyHelper is working"
```

No Postgres setup, no subscription, no machine-specific wiring. Then point any MCP agent at
`http://localhost:8765/mcp`, or follow the **[Getting Started guide](docs/GETTING_STARTED.md)** for
your first survey (~5 minutes).

> No API key but you run OpenClaw? Set `SURVEYHELPER_LLM_BACKEND=cli` to reuse its `claude -p`
> subscription (runs natively — see [Operations](docs/OPERATIONS.md)).

## Use it with OpenClaw (optional)

Make it *ambient* — it recognizes a paper you mention in chat and injects what your graph knows:

```bash
bash openclaw/install.sh                 # register the MCP server + skill
bash openclaw/plugin/install-plugin.sh   # install the ambient-recognition hook
```

The MCP server is a standard endpoint, so it works with Claude Desktop and other MCP clients too.

## How it works

Three pieces, all local:

- **MCP server** — what your agent calls; returns the instant card and queues the deep work.
- **Worker** — a background daemon that does the paced fetching, analysis, and synthesis.
- **Postgres + pgvector** — the memory: the paper graph, analyses, and your personal layer.

The instant card never waits on slow APIs; references and deep analysis fill in in the background.
Full detail in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Docs

- [Getting Started](docs/GETTING_STARTED.md) — zero to your first survey
- [Vision](VISION.md) · [Roadmap](ROADMAP.md) — what it is and where it's going
- [Architecture](docs/ARCHITECTURE.md) · [Operations](docs/OPERATIONS.md) — internals, running, troubleshooting
- [Contributing](CONTRIBUTING.md) · [Release process](RELEASE.md)

MIT licensed.
