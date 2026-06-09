# surveyHelper — Roadmap & Direction

The forward-looking plan. The original design draft (`plan.md`) and decision log
(`DECISIONS.md`) have been retired into git history now that Phases 0–1 are built and
verified; this file carries what's still live. For the running system see
[`README.md`](README.md), [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), and
[`docs/OPERATIONS.md`](docs/OPERATIONS.md).

---

## Where we are

**Phases 0–1 complete and verified live.** A fast literature-card plugin for OpenClaw:
- Sync `survey()` → instant card (steps 0/1/3/7, no LLM) in ~1–2 s, DB-cached
- Async worker enrichment → S2 `tldr` + references, with a **keyless arXiv-HTML reference
  fallback** so the citation graph survives S2 being down
- Postgres + pgvector store; cross-process rate limiter; `SKIP LOCKED` job queue with
  deferred retry; 5 MCP tools; launchd-persistent services; live Claude-agent E2E

**Honest framing:** today this is a *fast, resilient literature-lookup tool with clean
sync/async plumbing*. The hard infrastructure risks are retired. The **intelligence layers
(deep analysis, graph synthesis, personal memory, proactivity) are not built yet** — that is
where the product value still lives.

## Architecture invariants (load-bearing — keep these true)

1. **Single egress pacer.** Every paper-API call goes through `http.py` → the global,
   cross-process `rate_limit` bucket. PaperQA2 (Phase 2) must be network-isolated and fed
   through this layer, never calling S2/Crossref itself.
2. **DB-as-cache.** A stored paper/edge is never re-fetched; `paper_aliases` dedups every
   external id.
3. **Per-step status.** Each step records `ok|partial|failed|skipped`; a paper missing a
   source still yields a useful card rather than failing wholesale.
4. **Versioned analysis.** `paper_analysis` is keyed by `pipeline_version`; a better model
   adds a row, never a silent overwrite.
5. **Resumable jobs.** Job state + frontier live in Postgres; a crash or budget-stop resumes.
6. **Sync never blocks on the slow path.** The foreground card is arXiv-only; everything
   slow/throttled is the worker's job.

## Locked product decisions (still operative)

- **Standalone project** — not converging on the parent ambient-agent codebase.
- **LLM = the user's OpenClaw default** (Claude **Max** via the `claude-cli` runtime in the
  `generalops` gateway). The live session reads `~/.claude/.credentials.json` (it ignores
  `CLAUDE_CODE_OAUTH_TOKEN`); the durable fix is a synthesized credential from a long-lived
  `setup-token` (see memory `generalops-claude-auth`).
- **Depth-2 tiering:** full 0–7 on every paper (no cheap tier).
- **Trigger precision:** explicit intent only; fuzzy title → candidates.
- **Corpus:** arXiv / CS-first; architecture keeps the Unpaywall ladder for later breadth.
- **Embeddings:** local SentenceTransformers (no key); `EMBED_DIM` is one migration variable
  bound in two tables + their pgvector indexes.
- **Cost:** no hard caps yet — to be governed by a Phase-2 calibration run + pre-flight
  confirm + a cheap-`summary_llm` split, not guessed dollar caps.

## Build phases

| Phase | Scope | Status |
|---|---|---|
| 0 | Source + rate layer (arXiv/S2/GitHub behind one limiter + DB cache) | ✅ done |
| 1 | Cheap pipeline (steps 0/1/3/7) + canonical dedup + async enrich | ✅ done |
| 2 | Grounded deep steps (2/4/5/6) via `claude -p` whole-paper context + PDF/HTML full text | ✅ done (hardened) |
| 3 | MCP + OpenClaw (sync card fast, deep async) | ✅ done (card path) |
| 4 | **`expand`** — depth-2 BFS, dedup, budget, resumable frontier | ✅ done (no-LLM) |
| 5 | `synthesize` — lineage / open-problems / contradictions / landscape map | ✅ done |
| 6 | Personal layer — state, corrections, interests, personal dedup, **embeddings + similarity** | ✅ done |
| 7 | Proactivity — daily `proactive_scan` + digest, **semantic relevance filter** | ✅ done |
| 8 | Eval — golden set + regression run + cost dashboard | ◻ partial (faithfulness self-check + `usage_log`/`cost_summary`; golden set TODO) |

**All 8 phases implemented.** The next development arc — amplify synthesis, graph-aware
ambient conversation, trust/eval, and portability — is detailed in
[`docs/development-roadmap.md`](docs/development-roadmap.md).

## Open decisions (settle before the dependent phase)

1. **Phase-2 LLM routing (blocks everything intelligent).** PaperQA2 needs a programmatic
   chat-completions API, but Claude here is a subscription driven via `claude -p`. Options:
   (a) a thin LiteLLM adapter over `claude -p`; (b) `claude-max-api-proxy` (localhost:3456);
   (c) an Anthropic API key (cleanest, per-token cost). Note the 2026-06-15 subscription
   `claude -p` billing change.
2. **Embeddings source** for the personal layer (local ST vs OpenClaw `/v1/embeddings` if its
   provider exposes embeddings) and the final `EMBED_DIM`.
3. **Depth-2 cost guardrails** — calibrate real $/paper on the actual model before enabling
   `expand` + `analyze` together (see risk below).

## Known risks & mitigations

| Risk | State | Mitigation |
|---|---|---|
| **S2 reliability** (core value hung on a throttled free API) | mitigated | keyless arXiv-HTML ref fallback; S2 key would fully resolve (tldr + influence flags) |
| **Cost landmine** — Opus × full-0–7 × depth-2 ≈ $200–350/survey, no caps set | latent | build cost control *with* Phase 2/4: calibration + pre-flight confirm + cheap `summary_llm` split |
| **Auth fragility** — synthesized subscription credential, ~1 yr token, ToS-grey for `-p` | managed | documented in memory; API key is the robust alternative |
| **Embeddings unvalidated** — no GPU (MPS only); dim/speed untested at graph scale | open | load-test when Phase 6 lands; consider a small fast model (bge-small 384) |
| **No eval harness / cost tracking** — `usage_log` empty, quality unmeasured | open | wire before trusting Phase-2 output |

## Prioritized next steps

1. **(cheap, high value)** Semantic Scholar API key → complete cards (tldr + influence-ranked
   references) and working fuzzy-title search.
2. **(headline feature)** Settle open decision #1, then **Phase 2** — grounded deep analysis,
   built together with cost control (calibration + pre-flight confirm).
3. **(the graph payoff)** **Phase 4–5** — `expand` to depth-2 then `synthesize` (lineage /
   open problems / contradictions). This is the reason depth exists.
4. **(parallel track, no LLM dependency)** turn on embeddings → **Phase 6–7** personal layer +
   proactivity (the *memory* / *ambient* differentiators).
5. **(quality)** integration tests for the card/enrich/dedup paths; eval harness; `usage_log`.

## Note on historical design references

Code comments and docs cite `plan §N` / `DECISIONS §X`. Those refer to the retired design
docs, preserved in **git history** (`git show <rev>:plan.md`). They remain accurate as
rationale pointers; this ROADMAP supersedes them for forward direction.
