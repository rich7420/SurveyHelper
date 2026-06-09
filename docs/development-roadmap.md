# surveyHelper — Development Roadmap (post-v1)

All 8 plan phases are implemented. This roadmap is the *next* arc: amplify the one
genuinely scarce capability (graph synthesis), make the system **trustworthy** and
**portable**, and push the **ambient** dimension into the conversation itself. Each item
has a concrete acceptance gate, in the spirit of the original phased plan.

> **Guiding principle discovered in v1:** *trigger cost should match action cost.* Cheap
> actions (a DB/graph lookup) may fire liberally; expensive actions (LLM analysis, expansion)
> must be intent-gated, paced, and budgeted. This resolves the old "don't react to every
> mention" tension — you *can* react to everything, but only cheaply.

---

## Theme A — Graph-aware ambient conversation ⭐ (headline)

*"The graph reacts to what you're discussing."* Today the system acts on explicit commands
(`survey X`) and a daily scan. This theme adds a third, **conversational** trigger tier: when
a paper already in the graph (or near it) comes up in chat, surface what we know and quietly
deepen it in the background — the ambient pattern applied to the conversation, not just a timer.

**Three trigger tiers (refines the trigger-precision decision):**
1. *Explicit* ("survey / deep-dive X") → full pipeline (sync card + heavy async). *[exists]*
2. *Casual mention of any paper* → **cheap `recognize` (sync, no LLM)** + optional light
   background deepen. *[NEW]*
3. *Daily / idle* → proactive scan. *[exists]*

- **A1. `recognize(mention)` — cheap, liberal.** Resolve a mention against the graph (alias →
  title fuzzy → embedding nearest). Return, with **no LLM/API call**: do-we-have-it, the
  1-liner, your state/notes, whether it's deep-analyzed, and its connections (below).
  *Gate: mentioning an in-graph paper yields "I know this — <tldr>, you marked it read, it's
  2 hops from your FlashAttention line" in <200 ms, no network.*
- **A2. Deepen-on-mention (background).** If a recognized paper is in-graph but **shallow**
  (no deep analysis / thin neighborhood) **and** relevant (matches an active interest or
  mentioned repeatedly), enqueue a **low-priority** `deepen` job (selective analyze + small
  expand), paced + budget-gated. Discussing a paper quietly makes the system know it better
  for next time. *Gate: discuss an in-graph shallow paper → within minutes it gains deep
  fields + a few new edges, without an explicit command; budget-capped.*
- **A3. Connection surfacing.** `recognize` also returns graph distance to your read-set /
  interests (recursive CTE) + embedding-nearest analyzed papers. *Gate: "this connects to
  [X you read] (2 hops) and is similar to [Y]" is returned for an in-graph mention.*
- **A4. Conversation/session memory.** A lightweight log of papers discussed (per session)
  feeds proactivity and avoids re-surfacing. *Gate: a paper discussed today isn't re-surfaced
  by the daily digest.*

**Enabling work:** a `priority` column on `research_jobs` (user-requested > ambient-deepen);
`recognize` MCP tool; SKILL.md guidance to fire `recognize` on *any* paper mention (cheap) but
`survey`/`deep_dive` only on clear intent.

---

## Theme B — Amplify synthesis (the core value)

Synthesis is the scarce, differentiated capability. Make it richer and auditable.

- **B1. Selective deep-analysis during expand.** Deep-analyze the **top-K most-influential**
  nodes of an expansion (budget-bounded), so synthesis reduces over structured
  `key_components / key_numbers / limitations`, not just tldrs. *Gate: a depth-2 expand with
  `analyze_influential=true` produces a synthesis that cites specific methods/numbers from the
  references, within a stated $ budget.*
- **B2. Synthesis provenance.** Link every lineage / contradiction / open-problem claim back
  to the `paper_id`s it came from. Turns synthesis from a read-only blob into a navigable
  knowledge object. *Gate: `get_synthesis` returns, per claim, the source paper_ids; the agent
  can drill from a contradiction into the two conflicting papers.*
- **B3. Topic-level + incremental synthesis.** Synthesize over an *interest* or arbitrary set
  (`scope=topic`, already in schema), and re-synthesize cheaply as the graph grows. *Gate:
  `synthesize_topic("efficient attention")` reduces over all analyzed papers on that line.*

---

## Theme C — Trust (make the analysis believable)

The weakest dimension today: we ship LLM analysis whose quality is self-assessed.

- **C1. Golden-set eval harness.** ~15–20 hand-checked papers (incl. the Ulysses/Ring/BERT
  lines); on every `pipeline_version` bump, re-run and report per-step agreement + a
  faithfulness spot-check. *Gate: a version bump prints per-step agreement vs golden; a
  regressing version is flagged.*
- **C2. Independent faithfulness.** Verify with a *different* model (or extractive check)
  rather than the same model self-judging. *Gate: faithfulness verdicts come from a model
  distinct from the one that wrote the answer.*
- **C3. Contradiction verification.** Before reporting a synthesis "contradiction", verify the
  two cited papers actually conflict (targeted re-check). *Gate: reported contradictions are
  spot-checked to be real, not invented.*

---

## Theme D — Robustness & portability (toy → tool)

- **D1. Pluggable LLM (Anthropic API-key path).** A config switch between `claude -p`
  (subscription) and a direct Anthropic API key. Removes the fragile synthesized-credential +
  single-container liability, enables a proper cheap-summary / strong-answer split, and makes
  the repo reproducible for others. *Gate: `SURVEYHELPER_LLM_BACKEND=api` runs analyze/synthesize
  with no dependency on the generalops container.*
- **D2. LLM retry/backoff** in analyze/synthesize (parity with enrich's deferred retry).
  *Gate: a transient LLM failure defers the job instead of dead-lettering it.*
- **D3. Pre-flight cost confirm** wired into the user flow: before an expensive op, estimate
  (calibrated $/paper × N) and require confirmation over a threshold. *Gate: a large
  expand-with-analyze returns "≈N papers, ≈$C — confirm?" instead of silently running.*

---

## Theme E — UX & orchestration

- **E1. `deep_dive(paper)` meta-flow.** One call chains survey → expand → selective analyze →
  synthesize (budget-bounded), so the user doesn't hand-orchestrate. *Gate: `deep_dive(X)`
  yields a card immediately and a full synthesis when ready, in one user action.*
- **E2. Tool consolidation / SKILL guidance.** 16 tools is a lot; group + document when to use
  which so the agent chooses well.
- **E3. Proactivity threshold calibration.** Replace the guessed 0.62 cosine cutoff with a
  calibrated value (per interest, from labelled relevant/irrelevant examples).
- **E4. (parking lot)** graph visualization; multi-worker BFS; freshness re-scan of forward
  citations.

---

## Suggested sequencing

| Milestone | Theme | Why first |
|---|---|---|
| **M1** | B1 + B2 | Amplify + make auditable the one scarce capability (synthesis). Structured extraction already paved the way. |
| **M2** | A (A1→A4) | The headline ambient direction — turns the conversation into a trigger; highest novelty/value. Needs the job `priority` column. |
| **M3** | C (C1–C3) | Establish trust before leaning harder on the analysis. |
| **M4** | D1 (+ D2/D3) | Portability + robustness — the step from "my local toy" to "a tool others can run". |
| ongoing | E | UX polish as the above lands. |

**Rationale:** B makes the valuable part strong and auditable; A makes it *ambient* (the
original vision's soul); C makes it *trustworthy*; D makes it *portable*. Do them in that order
and each milestone independently increases the system's worth.
