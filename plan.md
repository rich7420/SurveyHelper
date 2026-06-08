# surveyHelper — Architecture & Build Plan

_Draft v2 · supersedes all earlier drafts (the voice-agent and `litgraph` versions are obsolete)._

---

## 1. What surveyHelper is

surveyHelper is a local research companion that runs alongside **OpenClaw**. When you discuss a paper in
chat, it fetches that paper, runs a structured 8-step analysis, recursively walks the citation graph to a
chosen depth, **synthesizes** what the graph means, remembers what *you* have read and care about, and
proactively surfaces new work on the lines you're following — all stored locally in **Insforge**.

It is deliberately the **ambient-agent pattern** in a research domain. The母-project (Junda's
`ambient-agent`) is about *visual / audio / **memory***, real-time, with an interaction model + an async
background model sharing context. surveyHelper is the same shape without the hard real-time audio
constraint:

| ambient-agent concept | surveyHelper realization |
|---|---|
| interaction model (foreground, real-time) | OpenClaw chat + instant card |
| background model (async, long-horizon) | the worker: analysis, graph synthesis, proactive scans |
| shared context / **memory** | Insforge: paper graph **+ your personal understanding layer** |
| proactive, perceives-and-acts | heartbeat-driven proactive surfacing of new relevant papers |

So surveyHelper has **three layers of value**, and the design treats all three as first-class:
1. **Per-paper analysis** — the 0–7 card (the atom).
2. **Graph synthesis** — lineage, open problems, contradictions across the expanded graph (the payoff of depth).
3. **Personal layer** — what you've read/understood, why you cared, corrections, and proactive surfacing
   (what makes it *memory* and *ambient* rather than a paper cache).

**Out of scope for v1:** training any model; a full GUI; multi-user. Single local user, leaning on
existing models and APIs.

---

## 2. Facts the design rests on (verified — see §17 for the log)

- **OpenClaw**: local-first agent; long-lived **Gateway** daemon; capabilities via **`SKILL.md`**;
  a **heartbeat** loop (~30 min) plus external triggers; **MCP-compatible**; model-agnostic.
- **Insforge**: open-source agent backend — **Postgres + pgvector**, auth, storage, edge functions,
  model gateway — over an **MCP server** + CLI; self-host via Docker (`localhost:7130`), Apache-2.0.
- **PaperQA2** (`paper-qa`, Future-House): SOTA grounded RAG over scientific papers — chunk+embed,
  map-reduce evidence, **in-text citations with provenance**, multi-provider metadata, retraction check,
  LiteLLM-compatible. → surveyHelper's extraction engine for the LLM steps.
- **Paper data sources**: **arXiv API** (metadata + PDF), **Semantic Scholar Graph API** (references,
  citations, `tldr`, `isInfluential`, batch), **OpenAlex** (graph + cross-check), **Unpaywall** (OA-PDF
  by DOI), **Crossref** (DOI + retraction), **GitHub API** + **HuggingFace Papers** (code).
- **Papers with Code is dead** (Meta retired it July 2025). Code lookup = arXiv/abstract GitHub-URL
  extraction → GitHub API → HF Papers.
- **Rate limits**: arXiv **1 req / 3 s, single connection** (429s even within, under 2026 load) → use
  1 req/4 s + backoff + cache; Semantic Scholar **key needed** (unauth = throttled shared pool);
  OpenAlex **moving to key-required** (Jan 2026 announce); Unpaywall free (email param).

---

## 3. Architecture & all-local topology

Three components, one clear division of labor, everything on your machine:

- **OpenClaw** owns **trigger + notify** (foreground, coarse). It detects you're discussing a paper and
  calls surveyHelper; on each heartbeat it reads pending notifications and tells you what's ready.
- **surveyHelper MCP server** is the **front door**: the tools OpenClaw calls.
- **surveyHelper worker** owns **paced execution** (background): all the slow, rate-limited, LLM-heavy
  work. A standalone daemon, independent of whether OpenClaw is up — this is where steady API pacing
  lives.
- **Insforge** is the **memory**: the paper graph, the analyses, and the personal layer.

```
   ┌─────────────────────────────── your machine ───────────────────────────────┐
   │                                                                             │
   │  OpenClaw Gateway ──MCP──► surveyHelper MCP server ──enqueue/read──┐        │
   │   (chat + heartbeat)            survey() get() graph()             │        │
   │        ▲ notify  ◄── pending_notifications() ─────────────────────┐│        │
   │        │                                                          ││        │
   │  surveyHelper worker (systemd/launchd/cron) ─────────────────────┘│        │
   │    job types: analyze · expand · synthesize · proactive_scan      │        │
   │    └─ global token buckets ─► arXiv · S2 · OpenAlex · Unpaywall · GitHub (net)
   │    └─ extraction engine: PaperQA2 ─► LLM endpoint (net)            │        │
   │                                                                   ▼        │
   │  Insforge (Docker, localhost:7130)  Postgres + pgvector  =  MEMORY          │
   │    papers · aliases · analysis · citations · embeddings · syntheses ·       │
   │    interests · paper_user_state · corrections · jobs · usage · notifications · settings
   └─────────────────────────────────────────────────────────────────────────────┘
        only egress: 5 read-only paper APIs + the LLM endpoint
```

Why the worker is separate from OpenClaw: OpenClaw's heartbeat is coarse (~30 min) and tied to OpenClaw
running — fine for "tell me when it's done," wrong for steady rate-limited pacing. Keeping execution in
one always-on worker also keeps the **rate limiter in exactly one place** (§9).

---

## 4. The unit of work — per-paper pipeline (steps 0–7)

A small DAG run for one paper. **Each step records its own status** (`ok | partial | failed | skipped`)
+ provenance, so a paper with no PDF still yields steps 0/1/3/7 instead of failing wholesale.

| Step | What | Source | LLM? |
|---|---|---|---|
| 0 | **Exists?** resolve id (or title-search → candidates) → canonical paper | arXiv / S2 / OpenAlex | no |
| 1 | **Purpose & pain point** | instant: S2 `tldr`; refine: PaperQA2 over intro | card no; refine yes |
| 2 | **Background / architecture** | PaperQA2 over method | yes |
| 3 | **Related papers** — backward **references** (default); forward citations optional, capped | S2 / OpenAlex | no |
| 4 | **Experimental method** | PaperQA2 over experiments | yes |
| 5 | **Results analysis** | PaperQA2 over results/tables | yes |
| 6 | **Limitations** (stated + inferred) + **retraction check** | PaperQA2 + Crossref/Unpaywall | yes |
| 7 | **Code open-source?** | GitHub-URL regex in PDF/abstract → GitHub API + HF Papers | verify only |

Three rules that make the deep steps work:
- **Extraction = PaperQA2, not hand-rolled.** Steps 1/2/4/5/6 are "grounded RAG over one paper," which
  PaperQA2 already does well (map-reduce evidence + in-text citations with page/section provenance). We
  pose each step as a structured question; we store the grounded answer. This is the main
  hallucination/cost de-risk. Validate fit in Phase 2; a thin home-grown map-reduce is the fallback.
- **Full-text ladder** (depth ≥ 2 papers are often not on arXiv): arXiv PDF → **Unpaywall**
  `best_oa_location.url_for_pdf` → **abstract + `tldr` only** (cheap tier, mark `coverage=abstract_only`).
- **Versioned & re-runnable.** Analysis rows carry `pipeline_version` + `model_used`; a better model
  later means a new row, never a silent overwrite — and lets the eval harness (§13) compare versions.

---

## 5. Sync vs async — the card, then the depth

**Sync (foreground, the paper you mentioned):**
- Return a **card with no LLM call** in ~2–5 s: steps 0/3/7 (pure API) + step 1 from S2 `tldr`.
- Enqueue the grounded deep steps (1-refine, 2, 4, 5, 6); they finish in the background and update the
  record. OpenClaw surfaces "deep analysis ready" on a later heartbeat.

**Async (background expansion, depth default = 2):**
- The worker does **BFS** over the graph: pop a paper, dedup, analyze at its tier, push neighbors, stop
  at `max_depth`.
- **Edge direction:** expand **backward references** by default (intellectual lineage — bounded,
  ~20–50/paper, stable). Forward citations optional and **capped** to top-N by `isInfluential` (famous
  papers have thousands).
- **Dedup authority:** resolve to a canonical key using **S2 paperId / OpenAlex work-id** (they already
  merge preprint+published); title-hash only as last resort; pgvector similarity as a backstop. Seen →
  add the edge, don't re-analyze. Also dedup against **your personal read-set** (§7) so the worker
  doesn't re-surface what you've already dismissed.
- **Tiered depth:** level-1 gets full 0–7; level-2+ get the cheap/abstract tier (0,1,3,7), promotable on
  demand. Full-depth-2 is explicit opt-in (cost).
- **Budget caps:** `max_depth` (2), `max_papers_per_job` (50), `max_refs_expanded_per_paper` (15 by
  influence), plus the §9 token budget.

---

## 6. Graph synthesis — the payoff of going deep (not just a pile of cards)

Expanding a citation graph is pointless if the output is N disconnected cards. After an `expand` job
finishes (or on request), the worker runs a **`synthesize` job** — a *reduce* over the analyzed
sub-graph for a root paper or a topic — producing:
- **Lineage**: how the idea evolved across the references (what each paper added).
- **Open problems**: limitations (step 6) recurring across the set, and what no paper has solved.
- **Contradictions / disagreements**: papers whose results or claims conflict (PaperQA2 supports
  contradiction detection; the citation edges say who responds to whom).
- **Landscape map**: clusters (pgvector) + the most-influential nodes in *your* analyzed set.

Stored in `syntheses` (keyed by root/topic + the set of papers + `pipeline_version`), re-generatable as
the graph grows or the model improves. This is what a surveying researcher actually wants, and it's the
reason depth exists.

---

## 7. Personal memory layer — what makes it *memory*, not a cache

The DB must remember **you**, not just papers:
- **`interests`** — the research lines you're actively following, each with an embedding. Seeded from
  what you trigger and what you explicitly add; used to focus synthesis and drive proactivity (§8).
- **`paper_user_state`** — per-paper, per-you state: `seen | read | understood | dismissed`, plus
  **why** it was triggered (the conversation intent / question that started it — not just a session id).
  Personal dedup uses this: don't resurface dismissed/read papers.
- This personalizes everything downstream: dedup, the relevance of proactive alerts, and the framing of
  synthesis ("relative to what you already understand, here's what's new").

Without this layer surveyHelper is a literature cache; with it, it's an agent that tracks your
understanding — the part most aligned with the母-project's "memory."

---

## 8. Proactivity — the ambient dimension

An ambient agent perceives and acts without being asked. surveyHelper does this through a low-frequency
**`proactive_scan` job** (e.g. daily, paced by the same token buckets):
- For each active interest / followed line, query arXiv + S2 for papers **new since the last scan** that
  cite your read-set or match the interest embedding.
- Dedup against `paper_user_state`; for genuinely new and relevant hits, run a cheap card and emit a
  **digest** notification ("3 new papers on your Ulysses-attention line; one rebuts [X you analyzed]").
- This reuses the worker, buckets, and notifications — no new machinery. It is the single feature that
  moves surveyHelper from passive tool to ambient agent, and it's why it's a good ambient-agent testbed.

Proactivity is **opt-in per interest** and **rate-limited to a digest** to avoid notification fatigue.

---

## 9. Rate limiting & the first-run setup interview

**One global, per-source token bucket, shared by foreground and background.** Sync card requests and
background BFS/scan draw from the *same* buckets, so a burst of foreground use automatically slows the
background instead of the two colliding into 429s. Buckets sized to verified limits:

| Source | Verified limit | Bucket default |
|---|---|---|
| arXiv | 1 req/3 s, 1 connection; 429s even so | **1 req / 4 s**, single-flight, backoff; `export.arxiv.org`; descriptive UA |
| Semantic Scholar | unauth = throttled shared pool; key needed | keyed RPS (start ~1; request more) |
| OpenAlex | 100k/day + 10/s historically; moving to key-required | 5 req/s, 50k/day; **use a key** |
| Unpaywall | free, email param | 5 req/s |
| GitHub | 5000 req/hr (token) | 1 req/s |

The DB is the cache: a stored paper/edge is never re-fetched. This + dedup is what makes depth-2
affordable on a 1-req/4-s arXiv budget.

**Setup interview (first run)** — writes `config.toml` + a `settings` row (single source of truth for
both MCP server and worker), asking three things:
1. **Exploration frequency** — how hard to drain the background queue. Default `gentle` = **1 paper / 30 s**
   (well under arXiv's limit even with retries); `normal` = 1/12 s; `aggressive` = 1/6 s (only safe with
   an arXiv higher-rate arrangement).
2. **API / token budget** — LLM cost cap **per job** and **per day** (the real cost driver), plus which
   keys are present (S2, OpenAlex, GitHub, Unpaywall email, LLM). Hitting a cap pauses the worker and
   notifies.
3. **Depth** — recursion depth per run. **Default 2**, with tiering + `max_papers_per_job`.

---

## 10. Storage (Insforge / Postgres + pgvector)

Principle: **separate immutable identity & graph (facts) from derived analysis (re-runnable) from the
personal layer (yours).**

```sql
-- identity & graph (facts)
papers(id pk, title, authors jsonb, year, venue, abstract,
       arxiv_id, doi, s2_id, openalex_id, url, pdf_url,
       text_coverage,            -- full | oa_pdf | abstract_only
       status, min_depth, retracted bool, created_at, updated_at)
paper_aliases(alias_id pk, paper_id → papers)          -- dedup backbone (every external id)
citations(src → papers, dst → papers, edge_type, is_influential,
          primary key(src,dst,edge_type))               -- the graph

-- derived analysis (re-runnable, versioned, per-step status)
paper_analysis(paper_id → papers, pipeline_version,
   step_status jsonb,            -- {0:ok,1:ok,2:partial,...}
   purpose, pain_point, architecture jsonb, method jsonb, results jsonb,
   limitations jsonb, code jsonb, provenance jsonb,
   model_used, analyzed_at, primary key(paper_id, pipeline_version))
paper_embeddings(paper_id → papers, kind, embedding vector(1536), primary key(paper_id,kind))
syntheses(id pk, scope, root_or_topic, paper_set jsonb,   -- §6 graph-level reduce
   lineage jsonb, open_problems jsonb, contradictions jsonb, map jsonb,
   pipeline_version, created_at)

-- personal layer (you)
interests(id pk, label, embedding vector(1536), active bool, created_at)  -- §7
paper_user_state(paper_id → papers,                         -- §7
   state,                        -- seen | read | understood | dismissed
   why text,                     -- the triggering intent/question
   interest_id → interests, updated_at, primary key(paper_id))
corrections(id pk, paper_id → papers, field, corrected_value jsonb,       -- §11
   note, created_at)             -- overlaid on reads; fed to future extractions

-- operational
research_jobs(id pk, type,       -- analyze | expand | synthesize | proactive_scan
   root_paper_id, requested_depth, current_depth, status, parent_job_id,
   triggered_by, budget jsonb, created_at, updated_at)
usage_log(id pk, job_id, source, calls int, tokens int, cost_usd, at)     -- cost tracking
notifications(id pk, job_id, kind, payload jsonb, digest_key,             -- digest_key groups
   delivered bool default false, created_at)
settings(key pk, value jsonb)    -- the setup-interview answers
```

Why this shape: re-running analysis or synthesis with a better model adds a row (new `pipeline_version`)
without touching identity or graph; `paper_aliases` makes dedup survive arXiv-vs-DOI duplication;
`citations` as edges makes depth traversal and graph queries plain SQL (recursive CTEs are fine to
depth 3 — no graph DB needed); the personal tables make dedup/synthesis/proactivity *about you*;
`corrections` are applied as an overlay on every read so a fixed analysis stays fixed.

---

## 11. Trust — human correction + faithfulness

A research tool that can't be corrected loses trust fast, and one that can't be measured can't be
improved (the FastVideo lesson, applied here).

- **Correction loop:** any analysis field can be overridden via a `correct_paper(paper_id, field, value,
  note)` MCP tool → `corrections` row. Reads return analysis **with corrections overlaid**. Corrections
  are also fed as context/few-shot to future extractions on related papers, and become eval signal.
- **Faithfulness, not just grounding:** PaperQA2 gives provenance (where a claim came from), but that
  isn't correctness. Every deep field stores its provenance so a claim is auditable back to a
  page/section; the eval harness (§13) checks a sample against hand-labeled truth.

---

## 12. OpenClaw integration (concrete)

- **MCP server `surveyHelper`** registered in OpenClaw config (stdio or HTTP — confirm current syntax).
  Tools: `survey(identifier|title, depth?, mode?)`, `get_paper(id)`, `get_graph(root, depth)`,
  `get_synthesis(root_or_topic)`, `correct_paper(...)`, `add_interest(label)`, `job_status(id)`,
  `pending_notifications()`.
- **`~/.openclaw/workspace/skills/surveyHelper/SKILL.md`** — tells OpenClaw *when* to call: user is
  discussing a specific paper → extract an identifier (arXiv id / DOI / title); if only a fuzzy title,
  `survey` returns candidates for one-line disambiguation. Also: don't fire on every passing mention —
  only on clear intent ("look into / survey / what about this paper") to avoid burning tokens.
- **`HEARTBEAT.md` hook** — each beat: call `pending_notifications()`; if any (deep-ready,
  synthesis-ready, proactive digest, budget-paused, failures), message the user; otherwise stay quiet.
- The split holds: OpenClaw = trigger + notify; worker = paced execution; Insforge = memory.

---

## 13. Quality / eval harness

Don't ship analyses you can't trust. Mirror the FastVideo discipline (measure the same way; compare
against a fixed reference):
- **Golden set:** ~15–20 papers (incl. ones you know well, e.g. the Ulysses/Ring/TGATE line) with
  hand-checked step-0–7 answers.
- **Regression run:** on every `pipeline_version` bump (model or prompt change), re-run the golden set
  and report per-step agreement + a faithfulness spot-check (does the cited provenance support the
  claim?). Don't promote a version that regresses.
- **Cost dashboard:** `usage_log` → tokens/$ per paper and per job; watch it as you tune tiering.

---

## 14. Expected environment

| Layer | Choice | Notes |
|---|---|---|
| Agent surface | **OpenClaw** Gateway (self-hosted) | add the surveyHelper skill + heartbeat hook |
| Front door | **MCP server** (Python, `mcp`/FastMCP) | OpenClaw + Insforge are MCP-native |
| Backend / memory | **Insforge** self-hosted (Docker, `localhost:7130`) | Postgres + pgvector + MCP |
| Worker | standalone Python daemon (**systemd/launchd**) or OS `cron` | owns token buckets; don't rely on pg_cron |
| Extraction engine | **PaperQA2 (`paper-qa`)**; `pymupdf`/GROBID under it | grounded; LiteLLM models |
| Full-text | arXiv PDF → **Unpaywall** → abstract+`tldr` | non-arXiv coverage |
| Paper APIs | arXiv, Semantic Scholar (**key**), OpenAlex (**key**), Crossref, Unpaywall (email) | behind §9 buckets + DB cache |
| Code lookup | GitHub API (**token**), HF Papers | PwC dead |
| LLM / embeddings | Claude/Codex via FastVideo account or local; embeddings → pgvector | cost driver, §9 capped |

Keys to line up: S2 key, OpenAlex key (free for academics), GitHub token, Unpaywall email, LLM access, a
running local Insforge project.

---

## 15. Initial setup

```bash
# 0. prereqs: docker, node, python 3.11+, OpenClaw installed
# 1. Insforge (memory) — local
git clone https://github.com/InsForge/InsForge && cd InsForge
cp .env.example .env && docker compose -f docker-compose.prod.yml up -d   # dashboard :7130

# 2. apply the §10 schema as an Insforge migration (confirm: MCP / CLI / raw SQL)

# 3. scaffold surveyHelper (MCP server + worker + extraction)
uv init surveyhelper && cd surveyhelper
uv add mcp httpx pymupdf pydantic paper-qa
cp .env.example .env   # S2/OPENALEX/GITHUB keys, UNPAYWALL_EMAIL, LLM key, INSFORGE_URL/TOKEN, ARXIV_UA

# 4. setup interview → config.toml + settings row
surveyhelper setup     # frequency [gentle], token budget per-job/day, depth [2] + tiering

# 5. start the worker (paced execution)
systemctl --user enable --now surveyhelper-worker

# 6. wire OpenClaw
#    register surveyHelper MCP; add SKILL.md (when to call survey); add HEARTBEAT.md notify hook

# 7. smoke test
#    chat: "survey arXiv:2310.01889" → card in seconds; deep + synthesis fill in async; heartbeat notifies
```

Done when: Insforge shows all tables + a `settings` row; `survey` returns a card for a known arXiv id;
the worker runs; `papers`/`paper_analysis` populate; a notification is delivered via OpenClaw.

---

## 16. Phased build plan (each phase, one acceptance gate)

| Phase | Build | Gate |
|---|---|---|
| **0** Source + rate layer | arXiv/S2/OpenAlex/Unpaywall/GitHub behind the §9 global buckets + DB cache | given an arXiv id: metadata + refs + GitHub URL, cached on 2nd call (no re-fetch) |
| **1** Cheap pipeline | steps 0,1(tldr),3,7 → `papers`/`citations`/`paper_analysis`; canonical dedup | one paper → correct card; re-run is a no-op |
| **2** Grounded deep steps | PaperQA2 for 1-refine/2/4/5/6 + full-text ladder + per-step status | **spike first**: confirm PaperQA2 fits; faithful method/results/limitations on a known paper |
| **3** MCP + OpenClaw | tools + SKILL.md + HEARTBEAT.md; sync card fast, deep async | chat mention → card in seconds + "deep ready" follow-up |
| **4** Async expansion | `expand` BFS + dedup + budget + tiering + edge direction | `survey(X, depth=2)` fills graph, no double-analysis, respects caps |
| **5** Synthesis | `synthesize` reduce → lineage/open-problems/contradictions/map | a depth-2 run yields a synthesis a human finds accurate |
| **6** Personal layer | `interests` + `paper_user_state` + personal dedup; `correct_paper` | dismissed papers don't resurface; a correction persists across reads |
| **7** Proactivity | `proactive_scan` daily + digest notifications | a new arXiv paper on a followed line is surfaced once, as a digest |
| **8** Eval | golden set + regression run + cost dashboard | a pipeline_version bump reports per-step agreement vs golden |

**Parking lot:** Kafka/Redpanda event plane (§18), graph-viz UI, multi-worker BFS, freshness re-scan of
forward citations, version-drift handling (v1 vs v3 as distinct).

---

## 17. Operational hardening (the small things that bite)

- **Pre-flight size estimate:** before an `expand`, estimate paper count (root's reference count ×
  branching); if it exceeds a threshold, return a "this job is large (~N papers, ~$C) — confirm?" rather
  than silently launching a huge run.
- **Freshness / TTL:** forward citations and citation counts go stale; stamp analyses and re-fetch
  graph edges on a TTL for papers on active interests.
- **Non-paper references:** reference lists contain websites, datasets, standards, software. The
  resolver must classify and skip non-papers gracefully, not stall.
- **Failure visibility / dead-letter:** papers that can't be fetched or analyzed go to a failed state
  with a reason; the worker retries with backoff, then surfaces "couldn't get full text for N papers."
- **Prompt-injection guard:** PDF text is untrusted and OpenClaw can exec on the host. Treat extracted
  paper text as data, never instructions; run the worker with least privilege; keep the surveyHelper
  skill scoped to research tools (no shell).
- **Notification digest:** batch completions (a depth-2 run that analyzed 40 papers = one digest, not 40
  pings).
- **Resumability:** per-step status + job state means a worker crash resumes mid-graph, not from scratch.

---

## 18. Where Kafka fits (not yet)

The worker + `research_jobs` table already *is* the async background pattern. Stay on a Postgres job
table (drained with `FOR UPDATE SKIP LOCKED`) for v1. Introduce Redpanda/Kafka only when you hit
**parallel workers**, **event replay/audit**, or **multiple consumers** (e.g. a live graph-viz UI). Name
the worker's events now (`paper.discovered`, `paper.analyzed`, `edge.found`, `synthesis.ready`) so the
later swap to a real event bus is cheap.

---

## 19. Open decisions (settle early)

1. **LLM model + budget** for extraction; hard per-job token cap (depth-2 blowup).
2. **Default depth-2 tiering**: full 0–7 vs cheap-tier-with-promotion.
3. **Trigger precision**: explicit "survey this" only, or any paper mention.
4. **Corpus scope**: arXiv/CS-first, or general (raises the Unpaywall/Crossref full-text weight).
5. **Converge toward the real ambient-agent codebase**, or stay a standalone testbed? (Affects how much
   to invest in §7–§8.)

---

## 20. Verification log

**Confirmed (current sources):**
- OpenClaw: Gateway daemon, SKILL.md, heartbeat (~30 min) + external triggers, MCP-compatible, local-first.
- Insforge: open-source agent backend, Postgres + pgvector, MCP + CLI, Docker self-host (:7130), Apache-2.0.
- PaperQA2 (`paper-qa`, Future-House): grounded RAG, map-reduce/RCS, multi-provider metadata, retraction
  check, LiteLLM. → adopted as the extraction engine.
- arXiv API: 1 req/3 s single connection (429s even within, 2026 load); `export.arxiv.org`; UA expected.
- Semantic Scholar Graph API: `/graph/v1`, references/citations/`tldr`/`isInfluential`/batch; unauth =
  throttled shared pool, **key needed**; metadata/graph only (not full text).
- OpenAlex: historically 100k/day + 10/s + mailto polite pool; **announced Jan 2026 a move to
  key-required**. → assume a key; confirm exact state at setup.
- Unpaywall: free `/v2/{doi}?email=`, returns `is_oa` + `best_oa_location.url_for_pdf`.
- Papers with Code: retired by Meta July 2025 → don't depend on it.

**Assumed / verify at build:**
- PaperQA2 fit as the structured per-paper extractor (Phase-2 spike) + its default model/embedding cost.
- Exact current S2 / OpenAlex limits + key turnaround (both changing through 2026).
- OpenClaw's current MCP-registration syntax + HEARTBEAT.md hook.
- Insforge migration mechanism for §10; whether its Postgres ships pg_cron (not relied on).
- Whether the FastVideo Claude/Codex account can serve as the extraction LLM endpoint.