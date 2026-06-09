# surveyHelper — Roadmap & Direction

The forward-looking plan. The original design draft (`plan.md`) and decision log
(`DECISIONS.md`) have been retired into git history now that Phases 0–1 are built and
verified; this file carries what's still live. For the running system see
[`README.md`](README.md), [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), and
[`docs/OPERATIONS.md`](docs/OPERATIONS.md).

---

## Where we are

**All 8 phases + the ambient-conversation foundation are built and verified live.**
~3,000 LOC, 44 tests, 16 MCP tools, 3 always-on services, an installed OpenClaw hook plugin.

The full value chain runs end-to-end:
> survey → instant card → background enrich → expand to a depth-2 graph → **synthesize**
> (lineage / contradictions / open problems) → remember what you read & think → **semantic**
> daily digest → **ambient recognition** (mention a paper in chat → the agent already knows it,
> your state, and "2 hops from what you read", injected with no tool call).

**Progress, honestly — the funnel:**
`papers 1,347 → cards 66 → deep-analyzed 2 → syntheses 1`. The machinery exists and works; the
**graph is still a skeleton** — breadth (edges) far exceeds depth (analyzed content). Proven
capabilities are real (the BERT synthesis surfaced genuine contradictions for \$0.09; the hook
injects graph context before the model runs), but most nodes are bare stubs. **Today the value
is in the shape and the proven capabilities, not in how much of the graph has substance.** The
next arc is depth + trust, not new breadth. See [`VISION.md`](VISION.md) for the deeper read.

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

## Decisions now settled (were open)

1. **LLM routing → `claude -p` adapter.** `llm/claude_cli.py` runs `docker exec … claude -p
   --output-format json` (tools disabled, usage/cost metered). Verified ~3.5 s/call. *(An
   Anthropic API-key backend remains the portability upgrade — see next steps M4.)*
2. **Embeddings → fastembed bge-small (384-dim, onnx, no torch).** `EMBED_DIM=384`; HNSW index
   added; semantic similarity + proactive relevance verified.
3. **Cost guardrails → daily circuit-breaker + cheap analyze model + calibration via
   `usage_log`.** Pre-flight confirm before big expands is still TODO (M1).

## Known risks & current state

| Risk | State |
|---|---|
| S2 reliability | **mitigated** — keyless arXiv-HTML ref fallback; S2 key would still upgrade tldr + influence flags |
| Cost of deep analysis | **bounded** — daily budget breaker + haiku default (~\$0.36/paper full-text); pre-flight confirm still TODO |
| Auth fragility | **resolved** — the API-key backend (M4) needs no synthesized credential; the `cli` subscription path remains optional |
| **Skeletal graph** (breadth ≫ depth) | **open** — synthesis is thin where nodes aren't analyzed → M1 selective depth |
| **Unverifiable synthesis** (the value *is* the risk) | **open** — self-graded groundedness ≠ correctness; relational claims have no single source; depth compounds analysis errors → M2 builds verifiability *into* synthesis (L2 spans + L4 abstention), VISION §5 |
| **Not portable** | **resolved** — `docker compose up -d` + an API key; no generalops/subscription coupling (M4) |

## Related work & honest positioning

surveyHelper is not the first AI lit-review tool. Knowing the field sharpens what's actually
differentiated (and what isn't):

| Tool | What it does | Overlap / what they have that we don't |
|---|---|---|
| **Scite** | "smart citations": supporting / contradicting / mentioning, at scale | **Contradiction detection itself is not novel** — Scite does it across 1B+ citations. |
| **Consensus** | claim → how much of 250M papers support/contradict | Scale + search we lack. |
| **Elicit** | 80-paper evidence matrices, risk-of-bias, structured extraction | Polished extraction + real users. |
| **NotebookLM** | synthesis, gap analysis, network maps over your sources | Synthesis UX + reach. |
| **[PaperQA2](https://github.com/Future-House/paper-qa)** (open source) | agentic RAG over papers with in-text citations, local full-text, **benchmarked on LitQA2** (85.2% precision) | The serious prior art. Has a **benchmark + SOTA numbers**; we have neither. |

**What is genuinely differentiated** (and worth doubling down on): not "we find contradictions," but
**(a) mechanical verbatim verification + honest abstention** (assert only two-sided quotes that a
program confirms exist in the source — most tools confidently assert relations), **(b) local-first +
bring-your-own-key**, **(c) relational *synthesis* (lineage/open-problems), not just per-claim
support**, and **(d) personal memory + ambient recall**. The academic framing is sound — see
*"Correctness is not Faithfulness in RAG Attributions"* (arXiv:2412.18004), which is exactly our
VISION §5 (groundedness ≠ correctness).

**What we lack vs all of them:** a benchmark, measured quality, and users. That drives the plan below.

## Next priority: evidence before features (R1–R5)

The mechanism exists; the **evidence that it produces correct, useful output does not**. Reuse
existing eval frameworks rather than reinventing — [FActScore](https://arxiv.org/abs/2305.14251)
(claim-decomposition faithfulness), [ALCE](https://arxiv.org/abs/2305.14627) (citation
precision/recall), [RAGAS](https://docs.ragas.io) (faithfulness metric); datasets/method from
[SciFact](https://github.com/allenai/scifact) and [LitQA2/LAB-Bench](https://github.com/Future-House/aviary).

- **R1 — Evaluation harness (highest priority).** A hand-checked golden set (~25–30 papers across
  2–3 domains, with known facts + real cross-paper tensions). Measure **analysis fact-coverage**
  (FActScore-style) and **synthesis precision *and recall*** (ALCE-style: are surfaced
  contradictions real? how many real ones are missed?), plus **run-to-run variance** of the verified
  count (the 0/1/2 jitter is a fragility signal). *Gate:* a reproducible `eval/` + `docs/EVALUATION.md`
  with real numbers. Builds on the deferred M2b (golden-set, DuckDB CSV-join).
- **R2 — Prove depth value in a *fresh* domain.** Deep-analyze 20–40 nodes in a non-NLP area; have a
  **domain expert** judge whether the synthesis surfaces real, correct lineage/contradictions.
  *Gate:* expert confirms ≥N verified tensions as true; R1 metrics don't collapse off the NLP set
  (tests prompt over-fitting).
- **R3 — Verify the *whole* synthesis + calibrated confidence.** Today only contradictions are
  verified; extend grounding to **lineage** (influence-style evidence: does B's text cite/extend A?)
  and open-problems, and replace binary verified/tentative with **strong/moderate/weak** tiers.
  *Gate:* lineage carries verification status; confidence tiers correlate with golden truth.
- **R4 — One real user.** Put it in front of 1–2 people doing an actual review for ~2 weeks; record
  which outputs they used vs ignored (validates the *premise* that contradictions — not lineage/gaps
  — are the scarce value, and that ambient injection helps rather than distracts). *Gate:* an honest
  usage log, even if it redirects the product.
- **R5 (later) — Scale/cost benchmark + the understanding model (M5).** Measure $/paper and the cost
  of synthesizing a whole field (the breadth≫depth economics); only invest in M5 once R1–R4 prove the
  base value.

*Sequencing:* R1 is the foundation (nothing is measurable without it); **R1 + R4 are highest
leverage** (internal numbers + external truth). Defer new features until these turn assumptions into
answers.

## Concrete next steps (feature milestones — secondary to R1–R5 above)

Ordered to close the distance to [`VISION.md`](VISION.md) Horizon 1 (a *grounded, trustworthy*
research memory). Detail + the OpenClaw-integration design live in
[`docs/development-roadmap.md`](docs/development-roadmap.md).

**M1 — Make synthesis substantive & auditable** ✅ *done*
- ✅ Selective deep-analysis of the **top-K most-influential** nodes during `expand`
  (`deep_dive` tool, `budget.analyze_influential`), so synthesis gains structured material.
- ✅ **Synthesis provenance:** every lineage/contradiction/open-problem claim cites its
  `paper_id`s; `get_synthesis` returns a `paper_index` to resolve them. Verified on BERT —
  contradictions drill to their exact sources (BERT vs ELMo/ULMFiT).

**M2 — Build verifiability INTO synthesis** *(trust is the same object as the value — VISION §5)*
The live `2/4 faithful` signal showed self-graded groundedness is weak, and synthesis (relational
inference with no single source) is the hardest thing to trust. Climb the trust ladder
(L0 self-graded → L2 evidence spans → L4 abstention) where it matters — *in synthesis*, not as a
bolt-on:
- **M2a — Mechanically-proven verification (L2 made real)** ✅ *done* — "verified" is no longer the
  verifier's say-so: its cited quotes are **string-matched (n-gram, extraction-noise tolerant) against
  the fetched source**, and survive only if verbatim AND two-sided. *Found and fixed real verification
  theater — the verifier had been paraphrasing; with a verbatim-demand prompt it now copies real spans,
  yielding 2 mechanically-confirmed BERT contradictions (e.g. "we added a randomly initialized BiLSTM
  on top. This does significantly hurt…").* Trust is now a program-checked fact, not LLM consensus.
- **M2a — Evidence + abstention, grounded in source (L1+L2+L4)** ✅ *done* — a cross-model verifier
  (haiku vs the sonnet synthesizer) now **fetches the cited papers' full text** and must quote a
  verbatim sentence from EACH side; one-sided or absent → **`tentative`** with the reason;
  `get_synthesis` surfaces a trust summary. *Live on BERT: the verifier quoted BERT's real
  section-3.1 sentence but found no ELMo counter-sentence — exposing that many "contradictions" were
  the synthesizer's **one-sided framing**, not documented disagreements.* This is the system reading
  the source, not summaries.
- **M2a — the iterative loop ("反覆查證")** ✅ *done* — the synthesizer is now **conservative**
  (proposes a contradiction only when both sides are documented), and `get_synthesis` **separates**
  verified `contradictions` (assert) from `tentative_tensions` (demote); the SKILL tells the agent to
  assert only verified. *Live on BERT: 5 one-sided/0-verified → 2/1-verified with a real ELMo quote;
  and through the agent — it asserted the verified one and said the other "shouldn't be stated as
  fact."* The north star ("honest about what it isn't sure of") is realized end-to-end.
  *(Optional further: re-search other sections before abstaining; this is the diminishing-returns tail.)*
- **M2b — Golden-set fact-coverage (L3, the DuckDB payoff):** a `golden.csv` of verifiable facts
  per well-known paper, joined against stored analysis via DuckDB (`--extra analytics`). This is an
  *analysis-layer* measure — do **not** conflate it with synthesis trust.
- **M2c — Surface trust:** expose groundedness / `tentative` flags on cards + synthesis so the
  agent caveats ("tentative / 2-of-4 grounded") instead of presenting all claims as equally solid.
- *Gate:* a synthesis marks its unverifiable contradictions `tentative`; each *asserted* contradiction
  links to two-sided source spans; the agent surfaces the trust flag.
- **Beware** the depth↔trust tension (VISION §5): richer synthesis fed by shaky deep analysis can be
  *more detailed and less reliable* — M2 must land alongside, not after, more depth.

**M3 — Finish the ambient loop** *(Theme A polish)*
- `agent_turn_prepare`/`message send` **proactive push-back** when a background deepen/synthesis
  finishes; **session memory** so a paper discussed today isn't re-surfaced by the digest.
- *Gate:* completing a deepen surfaces a message to your channel without waiting for the heartbeat.

**M4 — Make it portable** *(toy → tool)* — ✅ *core done*
- ✅ **Multi-provider** pluggable LLM backend (`SURVEYHELPER_LLM_BACKEND=anthropic|openai|gemini|
  cli|auto`) — set any one API key; `auto` picks the first present. SDK retry/backoff built in;
  prompt caching shares one paper-text prefix across analyze's 5 calls. The pipeline's Claude
  model is mapped to each provider's cheap/capable tier automatically.
- ✅ **One-command install**: `docker compose up -d` brings up pgvector (schema auto-applied) +
  worker + MCP — `ANTHROPIC_API_KEY` is the only required input. Verified from scratch (16 tables,
  `/healthz` ok). No `generalops`/subscription coupling on the compose path.
- *Remaining:* pre-flight cost confirm in the user flow; parameterize the mac-native launchd paths
  (the compose path already needs none).

**M5 — The understanding model** *(seed of Horizon 2 — "thinks with you")*
- Track what *you* understand vs the field; surface the **delta** on recognize/synthesis
  ("this rebuts what you marked understood last week").
- *Gate:* recognizing a paper that conflicts with something you marked `understood` flags the tension.

**Quick win (anytime):** a **Semantic Scholar API key** → complete cards (tldr + influence-ranked
references) and working fuzzy-title search; no code change, just `SEMANTIC_SCHOLAR_API_KEY`.

## Post-v1 follow-ups (after the first public release)

**Parquet analytics lane (at scale).** Postgres + pgvector stays the operational source of truth —
lookups, graph traversal, and vector similarity all need its indexes, so operational data must NOT
move to Parquet. But for the *analytics/eval lane* at scale, a **Postgres → Parquet snapshot export →
DuckDB** path is the right on-ramp (and beats the live postgres-scanner `ATTACH`, which we cross-tested
as slow + needing a runtime extension fetch). Where it wins once data is large: golden-set eval
(join `analysis` against `golden.csv`), `usage_log` time-series cost analytics, and cold
`paper_fulltext` archival (text compresses well in Parquet, keeping live Postgres lean).
*Trigger:* build a small `export_parquet` tool only when (a) data is genuinely large (~10k+ papers /
millions of usage rows) AND (b) there's an analytical workload that's slow on Postgres — premature
before that.

## Note on historical design references

Code comments and docs cite `plan §N` / `DECISIONS §X`. Those refer to the retired design
docs, preserved in **git history** (`git show <rev>:plan.md`). They remain accurate as
rationale pointers; this ROADMAP supersedes them for forward direction.
