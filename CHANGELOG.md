# Changelog

All notable changes to surveyHelper. Format follows [Keep a Changelog](https://keepachangelog.com/),
and this project aims to follow [Semantic Versioning](https://semver.org/).

## [0.1.1] — 2026-06-09

### Fixed
- **OpenClaw ambient plugin install from a clone.** The plugin's prebuilt `dist/index.js` was
  gitignored (global `dist/` rule) and therefore absent from the published repo; with no build step
  in the installer, the plugin could only be installed by the author. The prebuilt entry is now
  committed. Validated end-to-end: a fresh clone installs the plugin into OpenClaw and ambient
  recognition works.

## [0.1.0] — 2026-06-09

First public release. A local-first research companion: an MCP server + background worker (and an
optional OpenClaw ambient plugin) that turns a paper mention into a grounded, citation-graph-aware,
personally-remembered, **verifiable** research memory.

### Added
- **One-command install** — `docker compose up -d` brings up pgvector (schema auto-applied), the
  worker, the MCP server, and a daily proactive-scan scheduler. `ANTHROPIC_API_KEY` (or another
  provider key) is the only required input.
- **Multi-provider LLM backend** — `SURVEYHELPER_LLM_BACKEND=anthropic|openai|gemini|cli|auto`;
  set any one key. Prompt caching shares one paper-text prefix across analyze's calls.
- **Instant card** (no LLM): resolve → purpose → backward references → code link, in seconds.
- **Deep grounded analysis** (steps 2/4/5/6) with a faithfulness self-check.
- **Citation-graph synthesis** with **trust built in**: a conservative generator proposes
  contradictions, an independent cross-model verifier confirms each against the cited papers' full
  text by **mechanically matching verbatim quotes**, and unverifiable claims are downgraded to
  `tentative` (abstention). `deep_dive` deepens influential nodes then auto-synthesizes.
- **Personal memory** — interests, paper states (`understood`/`read`/…), and a proactive scan.
- **Ambient OpenClaw plugin** — recognizes a paper mentioned in chat (incl. natural phrasing like
  "the BERT paper") and injects what the local graph knows, with no agent tool call.
- **Operational robustness** — boot preflight (legible failures, password-redacted), a
  `surveyhelper-verify` self-test, idempotent schema-on-boot, cross-process egress rate limiting,
  resumable jobs, and an author-backfill maintenance script.
- Tooling: GitHub Actions CI (pgvector + full test suite), MIT license.

### Known limitations
- Method nicknames absent from a paper's title (e.g. ELMo → "Deep contextualized word
  representations") need a method-alias map for ambient recognition — not yet built.
- Authors are only available for papers with an arXiv id; S2-only reference stubs have none.
- The OpenClaw ambient plugin installs manually via `openclaw/install.sh` (ClawHub distribution
  is planned for a later release). The MCP server itself works with any MCP client.
- Synthesis is non-deterministic; the count of verified contradictions varies run to run.

### Post-v1 (see ROADMAP.md)
Method-alias recognition, ClawHub plugin distribution, a Parquet/DuckDB analytics lane at scale,
golden-set fact-coverage eval, and the "understanding model" (track what *you* know vs the field).
