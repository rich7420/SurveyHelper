# surveyHelper — Vision

A deep, honest account of what this system *is*, why it's valuable, where it falls short
today, and what it could become. For *what's built* see [`ROADMAP.md`](ROADMAP.md); for the
*next development arc* see [`docs/development-roadmap.md`](docs/development-roadmap.md). This
document is the north star and the honest mirror.

---

## 1. What surveyHelper really is

It is easy to describe surveyHelper as "a tool that fetches and summarizes papers." That
description is true and misses the point.

surveyHelper is an attempt at **externalized research cognition** — a local, always-on system
that maintains a persistent, grounded model of *a research landscape* and of *your evolving
understanding of it*, and that engages with that model **ambiently**, in the flow of your
conversation, rather than only when explicitly summoned.

Concretely, it holds three kinds of memory:

- **Factual memory** — the citation graph (papers, edges, identities), deduped and cached.
- **Interpretive memory** — grounded analysis and, above it, **synthesis**: lineage,
  contradictions, open problems across a sub-graph.
- **Personal memory** — what *you* have read, understood, dismissed, corrected, and the lines
  you follow; and the connections between a new paper and that history.

The bet is not any single layer. The bet is the **integration**: a system where the graph, the
synthesis, your understanding, and the conversation are one fabric.

---

## 2. Why it's valuable — what's scarce

The value is concentrated, not uniform. Most of what surveyHelper does (fetch a paper, show a
card) is table-stakes. Two things are genuinely scarce:

**(a) Synthesis grounded in *your* evolving graph.** Turning a citation neighborhood into
lineage / contradictions / open problems — *"how did this idea evolve, and where do these
papers disagree"* — is something retrieval tools don't do and notes tools can't. When run over
BERT's references it surfaced the real debates of that line (unidirectional vs bidirectional
pretraining; supervised vs unsupervised signal; recurrence vs attention). That is synthesis,
not summarization, and it cost \$0.09 because it reduces over cheap cards.

**(b) Ambient, grounded conversational memory.** When you mention a paper, a hook injects *"you
already have this — here's the tldr, you marked it read, it's 2 hops from FlashAttention which
you read"* **before the model even responds**, with no tool call. Research memory that surfaces
itself in conversation, tied to a live graph, is a genuinely new interaction.

**Against the field:** Connected Papers draws graphs but has no memory of you and no synthesis;
Elicit/SciSpace answer per-paper questions but keep no persistent personal graph; Obsidian/Notion
hold notes but aren't grounded in a live citation graph with LLM synthesis. surveyHelper's wager
is the *combination of all four*, local-first. **No single competitor occupies that intersection.**

---

## 3. What it demonstrates (beyond its own use)

Even setting aside its direct utility, the project is a working reference for patterns that are
hard to get right:

- **"Trigger cost matches action cost."** Cheap perception (a hook + DB lookup) may fire on
  every message; expensive action (LLM analysis, expansion) is gated, paced, budgeted. This is
  the principle that makes an ambient agent affordable.
- **Local-first ambient architecture:** sync foreground + async worker + one shared store, with
  cross-process coordination (a Postgres-ticket rate limiter, a `SKIP LOCKED` job queue) and a
  clean repo boundary that makes the storage backend swappable.
- **Reusing a subscription LLM programmatically** (the `claude -p` adapter) — pragmatic, and a
  pattern others will want.
- **OpenClaw integration done with the grain** — MCP tools for intent, a `before_prompt_build`
  hook plugin for ambient awareness, proactive `message send` for push-back.

The architecture is, today, **more mature than the content it carries** — well-built pipes,
modest payload. That is the correct order to build in, but it is the honest state.

---

## 4. Vision vs reality — the honest gaps

The integration is the value; it is also the fragility, because each layer is still shallow.

- **The graph is a skeleton.** ~1,300 nodes, ~66 cards, a handful deep-analyzed. Most of the
  "graph" is bare reference stubs. Synthesis is strong on well-trodden lines (BERT) and would be
  thin on sparse ones, because the material isn't there.
- **Quality is self-assessed.** Faithfulness is one model judging itself. We currently *ship
  analysis we cannot independently trust* — the very thing the plan warned against.
- **It isn't portable.** It depends on one machine, one Claude subscription, a synthesized
  credential. Its outward value is near zero until the LLM/auth layer is pluggable.
- **Deep analysis is expensive and slow** (~\$0.36, ~100 s/paper), so "analyze the whole graph"
  is not economical — depth must be *selective*, not uniform.

So the honest summary: **surveyHelper has crossed from "literature cache" into "research
companion with a synthesis spark and an ambient nerve," but the value today lives more in its
shape than in the depth of any one layer.**

---

## 5. The epistemic crux — trust is not a later phase; it is the same object as the value

The first live deep-analysis run scored one paper **2/4 faithful** — half its claims unsupported
by the source — while the agent built a confident synthesis on top. That number is not a bug; it
is a window onto the hardest truth about this system.

**We have been measuring the wrong thing.** "Faithfulness" measures *groundedness* (is this in
the source?) — necessary, but neither *correctness* nor *relevance*. A 4/4 analysis can faithfully
extract trivia and miss the point; a 2/4 can carry two correct *inferred* claims not literally in
the text. Conflating groundedness with quality is a category error.

**Synthesis is harder to trust than analysis — categorically.** Analysis is *extraction*: each
claim has a single source and can be checked against it. Synthesis is *relational inference* —
"these two papers contradict" lives in *no single paper*; the model imposes the frame. Is the
BERT-vs-ELMo "contradiction" real, or a rhetorical opposition of two coexisting design choices?
There is no single source to check it against. **The scarce value and the hardest trust problem
are the same object: synthesis.**

**And depth can trade against trust.** Synthesis reduces over analysis; feeding it richer-but-
shakier deep analysis (as selective depth does) can make the output simultaneously more detailed
and *less* reliable — errors are inherited and compounded.

**Trust is a ladder, and we are on its lowest rung:**

| Level | Mechanism | Status |
|---|---|---|
| L0 | self-graded faithfulness (same model) | **we are here** |
| L1 | cross-model verification | reduces error; correlated hallucination remains |
| L2 | **extractive grounding** — each claim links to a verbatim source span (machine-checkable) | the real bar |
| L3 | golden-set agreement vs human truth (sampled) | |
| L4 | **calibrated abstention** — the system knows what it doesn't know and says so | the real bar |

"Use a different model" (L1) helps but cannot solve correlated hallucination — models trained on
similar data share blind spots. Real trust lives at **L2 + L4**: claims mechanically verifiable
against source spans, and a system that *downgrades to tentative* when the evidence isn't there
rather than asserting confidently.

**The implication is structural:** trust cannot be a bolt-on. Because the value *is* the synthesis
and the risk *is* the synthesis, verifiability must be built **into** synthesis:
- provenance graduates from "cites which papers" to "links to the evidence spans" (L2);
- synthesis **abstains** — a contradiction is marked *tentative* when two-sided evidence is missing (L4);
- groundedness, correctness, and relevance stop being one number.

---

## 6. Where it's going — three horizons

**Horizon 1 — A *verifiable* research memory (near).**
Make the scarce layer substantive *and trustworthy in the strong sense* (§5). Substantive:
*selective* deep-analysis of the influential nodes so synthesis has real material (done — M1/B1).
Trustworthy: push verifiability **into** synthesis — provenance graduates from "cites which
papers" (done — M1/B2) to **evidence-span grounding** (L2), and synthesis learns to **abstain**,
marking a claim *tentative* when it can't find two-sided evidence (L4). A golden set (L3) measures
the analysis layer. The test of this horizon is not "the synthesis is rich" but "**you can trust
what it asserts, and it tells you when not to.**"

**Horizon 2 — A research thinking partner (mid).**
The system stops being something you query and becomes something that *thinks with you*. It
models not just the field but **your understanding of the field**, and surfaces the *delta*:
*"relative to what you concluded last week, this paper rebuts you"*; *"three papers on your line
share an unsolved limitation"*; *"this contradicts the result you marked as understood."* The
plan's personal layer (§7) sketches this; today it's barely built. This is where ambient memory
becomes genuinely cognitive rather than a fancy cache.

**Horizon 3 — A living model of a field (far).**
A system that maintains a model of a research area *over time*: what is genuinely new vs
derivative, where the field is stuck (recurring open problems), who disagrees with whom and how
that resolved, how an idea's lineage branches. It would tell you not just *what a paper says*
but *what it means for the field* and *for you*. Multi-modal (figures, equations, code, not just
text) and temporal (freshness, drift, re-synthesis as the field moves).

---

## 7. Improvement directions, by layer

**Factual (the graph)**
- Selective depth: analyze the most-influential nodes, not all — substance where it counts.
- Materialized graph metrics (centrality, distance) before recursive CTEs get hot; Apache AGE if
  graph work grows heavy.
- Multi-modal capture: figures, tables, equations, linked code — papers aren't only prose.

**Interpretive (analysis + synthesis)** — *the trust frontier (§5)*
- **Evidence-span grounding (L2):** every synthesis claim links not just to paper_ids (done) but
  to the verbatim spans that support it — machine-checkable, not model-asserted.
- **Abstention (L4):** mark a contradiction *tentative* when two-sided evidence isn't found;
  a synthesis that says "I'm not sure" beats one that's confidently wrong.
- **Separate groundedness / correctness / relevance** — stop collapsing quality into one number.
- Cross-model faithfulness + a golden set (L1, L3) — useful lower rungs, not the destination.
- Incremental + topic-level synthesis: re-synthesize as the graph grows; synthesize a *line*,
  not only a root paper.

**Personal (you)**
- The understanding model: track what *you* understand vs the field, and surface the delta — the
  single highest-leverage step toward "thinking partner."
- Session memory + proactive push-back: the conversation informs proactivity; finished deepening
  surfaces itself promptly.
- Calibrated relevance: replace guessed thresholds with learned ones.

**Foundation (trust + reach)**
- Pluggable LLM (API-key path) → robust, portable, reproducible; toy → tool.
- Cost as a first-class, *visible, confirmed* dimension — pre-flight estimates, not silent spend.
- Eval-as-companion (DuckDB over a golden set) — proven trustworthy, not asserted.

---

## 8. North star

> **A local, always-on partner that maintains a grounded, personal model of the research you care
> about — and thinks with you in the flow of conversation: surfacing the lineage you didn't trace,
> the contradiction you missed, and the gap between what the field knows and what you do —
> *grounded in evidence you can check, and honest about what it isn't sure of.***

Everything in the roadmap is in service of closing the distance between that sentence and what the
system does today. The shape is right. The work is to give each layer enough depth that the
*integration* delivers — and to make what it asserts **verifiable**, because a research partner you
cannot trust is not a partner. Trust is not the last phase; it is the same object as the value.
