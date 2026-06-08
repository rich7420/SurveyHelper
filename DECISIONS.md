# surveyHelper — Locked Decisions (settles plan.md §19)

_Companion to `plan.md`. This file records the decisions that were open in plan.md §19,
plus the research-verified corrections to the facts plan.md rests on. When this file and
plan.md disagree, **this file wins** (it is newer)._

Date settled: 2026-06-08.

---

## A. The five §19 open decisions — now locked

| # | Decision | **Locked answer** | Consequence |
|---|---|---|---|
| ⑤ | Project positioning | **Standalone project.** Ignore the母-project (Junda's ambient-agent) entirely — no convergence, no shared interface. | §7–§8 (personal layer / proactivity) are still built, but purely as surveyHelper features, not to mirror anything external. |
| ① | LLM endpoint + budget | **Reuse the user's OpenClaw default LLM** via OpenClaw's OpenAI-compatible Gateway endpoint (see §B). No separate LLM key. **Default model = Opus; NO per-job cost/token cap set** (user preference — tune from experience). Cost is governed by a Phase-2 calibration run + the §17 pre-flight confirm + a cheap-`summary_llm` split — see §D. Made visible & confirmed, not capped. | The plugin carries no LLM credential of its own; cost tracking still flows to `usage_log`. |
| ② | depth-2 tiering | **Full 0–7 on every paper** (no cheap/abstract tier). | More complete, more expensive. Cost is bounded instead by `max_papers_per_job` + the §17 pre-flight estimate + the $1/job cap (see §D). |
| ③ | Trigger precision | **Explicit intent only** ("survey / look into / what about this paper"). Fuzzy title → return candidates for one-line disambiguation. Do **not** fire on passing mentions. | Keeps token burn down; matches plan.md §12 SKILL.md guidance. |
| ④ | Corpus scope | **arXiv / CS-first** for v1. | Golden set is CS (Ulysses/Ring/TGATE); arXiv PDF gives the cleanest full-text path. The Unpaywall full-text ladder stays in the architecture, so widening to general domains later needs no re-architecture. |

---

## B. LLM sourcing — how the worker reuses OpenClaw's default LLM (resolves the sub-decision ⑤ opened)

OpenClaw's Gateway exposes an **OpenAI-compatible HTTP API** (verified against docs.openclaw.ai/gateway/openai-http-api):

- Endpoints: `POST /v1/chat/completions`, `POST /v1/embeddings`, `GET /v1/models`, `POST /v1/responses`.
- **Disabled by default** — must enable: `gateway.http.endpoints.chatCompletions.enabled: true` in `openclaw.json`.
- Auth: Gateway token (`Authorization: Bearer <OPENCLAW_GATEWAY_TOKEN>`), token mode.
- Model routing: send `model: "openclaw/default"` → runs `agents.defaults.model.primary`.

**Worker config:**
```
api_base = http://127.0.0.1:18789/v1
api_key  = <OPENCLAW_GATEWAY_TOKEN>   # from the mounted ~/.openclaw/.env
model    = openclaw/default           # PaperQA2 llm + summary_llm both point here
```
This means: **no provider key in surveyHelper**, no reading secrets off disk, OpenClaw's exact
routing/credentials reused. This supersedes plan.md §14's "Claude/Codex via FastVideo account" line.

**This machine runs OpenClaw in Docker** → for the host-side worker to reach the Gateway we need:
- the Gateway port published to the host: `-p 127.0.0.1:18789:18789`,
- `gateway.auth.mode: "token"` (keep it; do **not** expose operator-privileged Gateway on the LAN),
- the `~/.openclaw` dir bind-mounted to a host path so the worker can read `OPENCLAW_GATEWAY_TOKEN`.

> ⚠️ Anything that can call `/v1/chat/completions` is treated as a full OpenClaw **operator**. Protect the token; bind to `127.0.0.1` only.

---

## C. Embeddings — PARKED with a default (sub-decision, only needed at Phase 2)

PaperQA2 needs an embedding model (chunk→embed→retrieve), and pgvector needs embeddings for
dedup-backstop / interest matching / clustering (§5/§7/§8). The user's OpenClaw default model is a
**chat** model (likely Anthropic, which has no embeddings), so `/v1/embeddings` may not be usable.

- **Default plan:** local **SentenceTransformers** via `paper-qa[local]` (`st-` prefix) — fully local,
  **no key** (consistent with "only GitHub token available"), fits the all-local ethos.
- **Consequence:** local models are not 1536-dim → make the pgvector dimension a **config value**
  (plan.md §10 hardcodes `vector(1536)`; change to `vector(:EMBED_DIM)`), pick one model, keep it stable.
- **Revisit if:** OpenClaw's `/v1/embeddings` turns out to expose an embeddings-capable provider on the
  live instance — then we can switch and standardize on 1536-dim. Verify at Phase 2.
- **Schema touch-points (feedback #5):** the embedding dimension is bound in **two** tables
  (`paper_embeddings.embedding`, `interests.embedding`) **and** both of their pgvector indexes
  (ivfflat/hnsw bind the dim). Make `EMBED_DIM` a single migration variable — changing the model means
  updating all four together, don't hardcode `1536` in two places.
- **No CUDA GPU on this Mac** (Apple Silicon → SentenceTransformers can use MPS, faster than CPU but not
  free). Factor embedding time into the time/cost estimate for large graphs; consider a small fast model
  (e.g. bge-small / gte-small, 384-dim) and accept lower dim for speed.

---

## D. Cost control — Opus, no caps, made visible not capped (resolves ②/① + feedback #2; updated for the Opus decision)

**Decided:** OpenClaw's default = **Opus-class**, and **no per-job cost or token cap is set** (user
preference — tune from experience). Opus is the expensive end, so the job here is to make cost **visible
and confirmed**, not capped.

Per-paper, **full 0–7** ≈ 5 grounded PaperQA2 queries ≈ ~50–60 LLM calls ≈ ~60k input + ~7.5k output
tokens. At Opus pricing (~$15/M in, ~$75/M out) ≈ **~$1.5 / paper**. The summary step (re-summarizing
top-`evidence_k` chunks per query) is ~90% of those calls.

Because ② is *full 0–7 on every paper* and depth-2 fans out (`max_refs_expanded_per_paper`=15 → L0:1,
L1:15, L2:up to 225 before dedup), the **per-survey** cost on Opus is:

| Survey | papers | Opus full-0–7 (~$1.5/paper) | with `summary_llm`=cheap split (~$0.3/paper) |
|---|---|---|---|
| single foreground paper (no expand) | 1 | ~$1.5 | ~$0.3 |
| depth-1 (root + ~15 refs) | ~16 | ~$23 | ~$4.5 |
| depth-2 (would-be capped at 50) | 50 | ~$73 | ~$14 |
| depth-2 **uncapped** fan-out (after dedup) | ~150–240 | **~$220–350** | ~$42–67 |

> ⚠️ An earlier draft said "~$24 for depth-2" — that undercounted the L2 fan-out. With Opus + full-0–7 +
> **no cap**, a single casual "survey this at depth 2" can be **$200–350**. This is the number to keep in
> view. The single foreground paper (~$1.5) is cheap; the depth-2 fan-out is where the money is.

**Resolved approach (no caps, per user — so these are confirms + model-routing, NOT limits):**
1. **Phase 0–1: no LLM, no cost.**
2. **Phase-2 calibration run** — analyze **one** known paper full-0–7 through the *actual Opus* and read
   `usage_log` → real $/paper and tokens/paper, grounding every estimate below in a measured number.
3. **No per-job token/dollar cap is set** (honoring the preference). The one safety strongly recommended
   to keep is **not a cap**: the **§17 pre-flight confirm** — before an `expand`, show "depth-2 here ≈ N
   papers ≈ $C, proceed? (a) full (b) depth-1 (c) top-K refs". On Opus with no cap this is what stands
   between a casual request and a silent $300. Expansion stays **by `is_influential`** so any bounding is
   the explicit "top-K most-influential refs," never a blind BFS cutoff (resolves #2). `max_papers_per_job`
   is **not** enforced as a hard stop (no caps) — kept only as an estimate input to the preflight.
4. **Highest-leverage saving that is NOT a cap — split the models:** point PaperQA2's high-volume
   `summary_llm` (the ~90% of calls) at a **cheap model** while keeping `llm` = Opus for the final
   grounded answer. ~**5× cheaper, quality-neutral** (depth-2 ~$73→~$14). Requires OpenClaw to expose a
   cheap model alongside Opus, targeted via the `x-openclaw-model` header — verify at Phase 2 (§F).
   Secondary knob: `evidence_k` 10→5 ≈ halves summary cost.

**Resumability across a stop (resolves #6):** every analyzed paper is committed to `paper_analysis`
**immediately** (not at job end), and the BFS frontier (queued paper ids + their depth/tier) is persisted
on the job. A token-breaker or budget stop sets job status `paused_budget` with the frontier intact;
confirming more budget **resumes from the frontier**, and the DB-is-cache rule means already-analyzed
papers are never re-paid. A stop therefore never wastes spent tokens. Needs a `job_papers(job_id,
paper_id, depth, tier, status)` queue table — drained `FOR UPDATE SKIP LOCKED` per plan §18 — or an
equivalent `frontier jsonb` on `research_jobs`.

---

## E. Research-verified corrections to plan.md facts (apply these at build)

All four core dependencies were verified real. Corrections found:

1. **OpenAlex — MAJOR CHANGE.** As of Feb 2026 OpenAlex **requires an API key**; the `mailto` "polite pool"
   is **discontinued**; model is now credit-based (~$1/day free tier). plan.md §9 still assumes the polite
   pool — **send a key, drop `mailto`**. (We have no OpenAlex key yet; CS-first lets us lean on arXiv + S2
   and treat OpenAlex as an optional cross-check until a key is provisioned.)
2. **Insforge env vars.** Not `INSFORGE_URL` / `INSFORGE_TOKEN`. Real names: **`API_BASE_URL`**
   (e.g. `http://localhost:7130`) + **`ACCESS_API_KEY`** (`ik_…`, admin) for server/MCP; client SDK uses
   `baseUrl` + `anonKey`. Schema/migrations: file-based `.sql` via `npx @insforge/cli db migrations up --all`
   or the MCP tool — arbitrary `CREATE TABLE` fully supported (real Postgres, not a locked abstraction).
3. **Insforge has pg_cron** (preloaded) + a Schedules feature, **and** a Deno Edge Functions runtime.
   plan.md §14 says "don't rely on pg_cron" — that was precautionary; it's actually available if we want it.
   Decision stands (own worker owns pacing), but pg_cron is a fallback for the daily `proactive_scan` tick.
4. **PaperQA2** = `paper-qa`, now **CalVer** (`2026.3.18`), Apache-2.0, needs **Python 3.11+** (this machine
   has 3.9 — use `uv` to pin 3.11+). Biggest cost knob: `answer.evidence_skip_summary`. LiteLLM-compatible
   (points at the OpenClaw `/v1` endpoint fine).
5. **arXiv** — keep 1 req/4 s + backoff: intermittent 429s reported even at the documented 1/3 s as of
   Feb 2026. Descriptive User-Agent is best practice but **not** an official requirement.
6. **Crossref** — new lower limits since Dec 2025 (polite pool: 10/s single, 3/s list); read the live
   `x-rate-limit-*` response headers rather than hardcoding.

---

## F. Open items to verify on the live instances (not blocking Phase 0–1)

- OpenClaw `/v1/embeddings`: separate enable flag? does the configured default provider expose an
  embeddings model? (drives §C).
- OpenClaw `model: "openclaw/default"` → `agents.defaults.model.primary` mapping + streaming/tool fidelity.
- **Security (drives §I):** can a plain `/v1/chat/completions` through the Gateway actually trigger
  OpenClaw tools / side-effects, or is it pure model routing? Determines whether the worker uses the
  endpoint or the secret-file fallback.
- **Cheap-model availability (drives §D.4):** does OpenClaw have a cheap model configured *alongside*
  Opus, reachable via the `x-openclaw-model` header? Needed for the `summary_llm`=cheap / `llm`=Opus
  split (~5× saving). If not, the summary step stays on Opus (~$1.5/paper).
- OpenClaw-in-Docker: confirm the gateway port is published to host `127.0.0.1:18789` and `~/.openclaw`
  is bind-mounted (so the worker can read the token).
- Insforge exact MCP tool names for raw-SQL / migrations (capability confirmed; literal tool id not).
- Semantic Scholar key turnaround if/when we request one (unofficial; unauth shared pool works to start).

---

## G. What this unblocks — and the Phase-1 "no LLM" caveat (resolves #1)

The build can start at **plan.md Phase 0** (source + rate layer) and **Phase 1** (cheap pipeline:
steps 0,1,3,7). These stay **LLM-free**, but only because step 1 uses a fallback ladder — S2 `tldr` is
**not present on every paper** (new / non-CS / obscure), so:

- **Step-1 card ladder (no LLM):** S2 `tldr` → else **first 1–2 sentences of the abstract** (extractive)
  → else `(no summary available)`. Store `step1_source: tldr | abstract_extractive | none` and mark the
  step `partial` when it falls back. The LLM **step-1-refine** is a separate Phase-2 enqueued job.
- The Phase-1 gate ("correct card") therefore means: card populated from tldr-or-abstract, source flagged
  — **not** "tldr always exists." This keeps Phase 1 genuinely LLM-free and the gate honest.

Beyond the optional GitHub token, Phase 0–1 need no key and run fully against a local Insforge.

---

## H. PaperQA2 must be network-isolated from the paper APIs (resolves #3 — Phase-2 invariant)

PaperQA2 has built-in multi-provider metadata fetching (S2 / Crossref / Unpaywall) — it will call those
APIs **itself**, bypassing the §9 global token buckets and colliding with the worker into 429s (the exact
bug the single-limiter design exists to prevent, just from a second source).

**Invariant:** the rate limiter stays the *single* egress point for paper APIs. PaperQA2 runs as a **pure
local extractor** — we pre-fetch the PDF and metadata through our buckets and hand PaperQA2 only local
files + explicit `DocDetails` (title/doi/citation via manifest or `aadd(..., citation=, docname=, doi=)`),
with its own metadata/search providers **disabled**. Retraction check (step 6) is done by *our* Crossref
client through the bucket, not PaperQA2's. Exact disable knobs confirmed in the Phase-2 spike.

---

## I. Operator-privilege of the OpenClaw /v1 endpoint vs an unattended worker (resolves #4)

§B's endpoint is operator-privileged, and the worker hits it **unattended** while feeding it **untrusted
PDF text** (§17 prompt-injection risk). Two mitigations + one tradeoff to settle:
- **Treat all extracted paper text as data, never instructions** — delimit it, label it untrusted; the
  worker never forwards paper text as a top-level instruction.
- **Verify** whether a plain `/v1/chat/completions` through that endpoint can actually trigger OpenClaw
  tools / side-effects, or is just model routing (open item, §F).
- **Tradeoff (decide at Phase 2):** if that endpoint can trigger tools, prefer the *secret-file fallback*
  — the worker reads the provider key from the mounted `~/.openclaw/.env` and calls the provider directly
  via LiteLLM. Ironically the "brittle" path is the more secure one: it never hands an unattended,
  PDF-fed daemon an operator handle. Decide once the §F verification lands.
