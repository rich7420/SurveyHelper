# surveyHelper — Architecture

How the running system fits together. For status, direction, and the locked decisions see
[`../ROADMAP.md`](../ROADMAP.md). (The original design draft and decision log are retired into
git history; code comments still cite their `plan §N` / `DECISIONS §X` section numbers as
rationale pointers.)

## Components (all local)

```mermaid
flowchart TD
    you([you]) -->|chat| ocw["OpenClaw gateway (Docker)<br/>Claude agent · SKILL.md · HEARTBEAT.md"]
    ocw -->|"MCP (streamable-http)"| mcp["surveyHelper MCP server<br/><i>front door, foreground</i><br/>survey · get_paper · get_graph"]
    worker["surveyHelper worker<br/><i>paced execution, async</i><br/>enrich · expand · analyze"]

    mcp -->|enqueue jobs| db
    worker -->|"claim (FOR UPDATE SKIP LOCKED)"| db
    mcp <-->|read / write| db
    worker <-->|read / write| db
    db[("Postgres + pgvector<br/>papers · aliases · citations · paper_analysis<br/>research_jobs · notifications · rate_limit")]

    mcp -->|paced via rate_limit| apis
    worker -->|paced via rate_limit| apis
    apis["arXiv · Semantic Scholar · GitHub<br/><i>only egress — behind the limiter + DB cache</i>"]
    db -. notifications .-> ocw

    classDef proc fill:#e8f0fe,stroke:#4285f4;
    classDef mem fill:#e6f4ea,stroke:#34a853;
    classDef ext fill:#fef7e0,stroke:#fbbc04;
    class mcp,worker proc; class db mem; class apis ext;
```

Three processes, one division of labor (plan §3):
- **MCP server** (`surveyhelper.mcp_server`) — the front door OpenClaw calls. Returns the
  instant card synchronously, enqueues background work. Stateless beyond the DB.
- **Worker** (`surveyhelper.worker`) — background daemon. Claims jobs `FOR UPDATE SKIP LOCKED`,
  runs them, notifies. Independent of whether OpenClaw is up.
- **Postgres+pgvector** — the memory *and* the coordination plane (job queue + rate-limit bucket).

## The two workflows, side by side

```mermaid
sequenceDiagram
    actor U as you
    participant O as OpenClaw agent
    participant M as MCP server
    participant D as Postgres
    participant W as worker
    U->>O: "survey arXiv:2310.01889"
    O->>M: survey(id)
    M->>D: cache check / resolve (arXiv only)
    M-->>O: instant card (~1–2s)
    M->>D: enqueue enrich (+ expand if depth=2)
    O-->>U: show card
    rect rgb(232,244,234)
    Note over D,W: background, concurrent
    W->>D: claim job (SKIP LOCKED)
    W->>D: S2 tldr + references<br/>(or arXiv-HTML fallback)
    W->>D: notification "enriched"
    end
    O->>D: heartbeat → pending_notifications()
    O-->>U: "deep analysis ready"
```

**Sync (foreground)** — `survey(id)` → ~1–2s:
1. parse identifier → `Ref`
2. DB-as-cache: if the card already exists, return it (no network)
3. step 0 resolve via **arXiv only** (never blocks on S2)
4. step 1 purpose — ladder: S2 `tldr` *(skipped here)* → abstract first sentences → none
5. step 3/7 from what's local; persist `paper` + `paper_analysis`
6. enqueue an `enrich` job; return the card

**Async (background)** — the worker drains jobs:
- **`enrich`** — fetch S2 `tldr` (upgrades step 1 → `ok`) and references (step 3 → graph edges).
  If S2 is throttled, defer with capped exponential backoff (`run_after`/`attempts`).
- **`analyze`** (Phase 2) — deep grounded steps via PaperQA2.
- *(future)* `expand` (BFS), `synthesize`, `proactive_scan`.

Both run **concurrently** and share one DB (memory) and one `rate_limit` bucket, so a burst of
foreground surveys automatically paces the background — never colliding into 429s.

## Key invariants
- **Single egress pacer.** Every paper-API call goes through `http.py` → the global `rate_limit`
  bucket. (PaperQA2 in Phase 2 must be network-isolated and fed via this layer — DECISIONS §H.)
- **DB-as-cache.** A stored paper/edge is never re-fetched (`paper_aliases` dedups every external id).
- **Per-step status.** Each step records `ok|partial|failed|skipped`; a paper missing S2 still yields
  a useful card (plan §4) rather than failing wholesale.
- **Versioned analysis.** `paper_analysis` is keyed by `pipeline_version` — a better model adds a row.
- **Resumable jobs.** Job state + frontier live in Postgres; a crash or budget-stop resumes, not restarts.

## Module map
```
surveyhelper/
  config · models (Pydantic) · logging_setup
  ratelimit (DB-backed bucket) · http (shared client + retry/backoff)
  db/      __init__(pool) · papers · analysis · jobs · notifications
  sources/ identifiers · arxiv · s2 · github
  pipeline/ resolve (step 0) · card (steps 0/1/3/7) · enrich (S2 async)
  worker · mcp_server
```
