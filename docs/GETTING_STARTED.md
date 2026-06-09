# Getting Started (≈5 minutes)

surveyHelper turns a paper you mention into a grounded, citation-graph-aware, *verifiable* research
memory. This walks you from zero to your first survey.

## 0. Prerequisites
- **Docker** (Desktop or Engine + Compose).
- **One LLM API key** — Anthropic, OpenAI, or Google Gemini. *(Or, if you run OpenClaw with a
  Claude subscription, you can use the keyless `cli` backend — see step 1.)*

## 1. Configure
```bash
git clone https://github.com/rich7420/SurveyHelper.git
cd SurveyHelper
cp .env.example .env
```
Open `.env` and set **one** provider key, e.g.:
```ini
ANTHROPIC_API_KEY=sk-ant-...      # or OPENAI_API_KEY=... or GEMINI_API_KEY=...
# SURVEYHELPER_LLM_BACKEND=auto   # auto-picks the provider whose key is set (default)
```
> No API key but you run OpenClaw? Set `SURVEYHELPER_LLM_BACKEND=cli` and skip the key — it reuses
> the container's `claude -p` subscription. (This path runs natively, not in compose — see README.)

## 2. Start the stack
```bash
docker compose up -d
```
This brings up four services: **db** (pgvector, schema auto-applied), **worker** (background
analysis), **mcp** (the agent-facing server on `http://localhost:8765`), and **scheduler** (daily
proactive scan). First run builds the image (a minute or two).

## 3. Verify it works
```bash
docker compose run --rm worker surveyhelper-verify
```
Expected:
```
→ surveying arXiv:1706.03762 (instant card path, no LLM) ...
  ✓ title:      Attention Is All You Need
  ✓ references: … tracked
✓ surveyHelper is working.
```
If the DB is unreachable or your key/backend is misconfigured, the **preflight** prints a one-line
fix instead of a cryptic error.

## 4. Your first survey

surveyHelper speaks **MCP** — point any MCP client at `http://localhost:8765/mcp` and call the
`survey` tool. Two easy ways:

**A. From an MCP-capable agent (Claude Desktop, OpenClaw, …)** — add the server, then just ask:
> "Survey arXiv 2201.11903 and tell me its purpose and how many references it has."

**B. From Python (no agent needed):**
```python
import asyncio, json
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession

async def main():
    async with streamablehttp_client("http://localhost:8765/mcp") as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            res = await s.call_tool("survey", {"identifier": "arxiv:2201.11903"})
            print(json.loads(res.content[0].text)["card"])

asyncio.run(main())
```

You get an **instant card** (purpose, references, code link) in seconds. References and the deeper
S2 metadata fill in **in the background** — re-run `survey`/`get_paper` a moment later to see them.

## 5. Go deeper
- `deep_dive(paper_id)` — expands the citation graph, deep-analyzes the most-influential
  references, then **auto-synthesizes**.
- `get_synthesis(paper_id)` — lineage, open problems, and **contradictions**. Only contradictions
  backed by *verbatim quotes from both papers* are asserted; the rest are labelled `tentative`.
  This is the point: surveyHelper tells you what it can prove and is honest about what it can't.
- `add_interest("...")`, `mark_paper(id, "understood")` — it remembers what *you* care about.

## 6. (Optional) OpenClaw ambient plugin
Make surveyHelper *ambient* — it recognizes a paper mentioned in chat and injects what your graph
knows, with no tool call:
```bash
bash openclaw/install.sh                 # register the MCP server + skill + heartbeat
bash openclaw/plugin/install-plugin.sh   # install the ambient recognition hook
```
Then in OpenClaw: *"I'm reading the BERT paper by Devlin et al"* → it surfaces what you already know.

## Where next
- Operations, upgrades, troubleshooting → [`docs/OPERATIONS.md`](OPERATIONS.md)
- What this is and where it's going → [`VISION.md`](../VISION.md) · [`ROADMAP.md`](../ROADMAP.md)
- Contributing → [`CONTRIBUTING.md`](../CONTRIBUTING.md)
