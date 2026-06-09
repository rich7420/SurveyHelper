# Release process

How surveyHelper is versioned and released. Two artifacts ship: the **system** (the repo: MCP
server + worker, run via Docker) and the optional **OpenClaw plugin** (published to ClawHub).

## Versioning
[SemVer](https://semver.org): `MAJOR.MINOR.PATCH`. Patch = bug fixes only; minor = backward-
compatible features; major = breaking changes. The repo tag and the GitHub Release share the
version (e.g. `v0.1.1`). The plugin has its own version in its `package.json` / `openclaw.plugin.json`.

## Branch & review model (post-v1)
Since v0.1.0 is public, **all changes go through GitHub issues + pull requests** — no direct commits
to `master`. Every PR must have **green CI** (`.github/workflows/ci.yml`: pgvector + full test suite)
before merge. Prefer squash-merge for a linear history.

## Cutting a system release

1. **Verify green + dogfood.** `master` CI green; run the newcomer path end-to-end from a fresh
   clone: `docker compose up -d` → `docker compose run --rm worker surveyhelper-verify` (see
   `docs/GETTING_STARTED.md`). Catch gitignored-artifact traps (e.g. `uv.lock`, plugin `dist/`).
2. **Update the changelog (via a PR).** In `CHANGELOG.md`, add a dated `## [X.Y.Z] — YYYY-MM-DD`
   section with Added / Fixed / Known-limitations. Merge it.
3. **Tag** the merge commit:
   ```bash
   git checkout master && git pull
   git tag -a vX.Y.Z -m "surveyHelper vX.Y.Z — <one-line summary>"
   git push origin vX.Y.Z
   ```
4. **Publish the GitHub Release** (notes from the changelog):
   ```bash
   gh release create vX.Y.Z --title "vX.Y.Z — <title>" --notes "<highlights + install pointer>"
   ```
   The newest non-draft, non-prerelease tag becomes `Latest` automatically.

## Publishing the OpenClaw plugin to ClawHub

The ambient plugin lives in `openclaw/plugin/surveyhelper/`. It ships a **prebuilt `dist/index.js`**
(committed — the installer has no build step), and its `package.json` carries the required
`openclaw.compat.pluginApi` + `openclaw.build.openclawVersion`. Publishing uses the **`clawhub`
CLI** (separate from `openclaw`), and needs a GitHub account that passes ClawHub's upload gate.

```bash
# one-time
npm i -g clawhub
clawhub login            # browser OAuth; or `clawhub login --device` headless
clawhub whoami

# from the repo root — dry-run first, then publish
clawhub package publish openclaw/plugin/surveyhelper --family code-plugin --dry-run
clawhub package publish openclaw/plugin/surveyhelper --family code-plugin
```
`--dry-run` runs preflight (validates the `openclaw` metadata) without uploading — fix anything it
flags before the real publish. After publishing, verify a clean install:
```bash
openclaw plugins install clawhub:openclaw-surveyhelper
```

**When the plugin changes:** rebuild and commit `dist/index.js`, bump the version in both
`package.json` and `openclaw.plugin.json`, then re-run `clawhub package publish`.

> Until the first ClawHub publish, the plugin installs from a clone via
> `bash openclaw/plugin/install-plugin.sh` (this works for everyone as of v0.1.1).

## Pre-release checklist
- [ ] `master` CI green; `uv run pytest -q` passes locally
- [ ] Fresh-clone dogfood: `docker compose up` + `surveyhelper-verify` succeed
- [ ] Plugin installs from a clone (and, once published, via `clawhub:`)
- [ ] `CHANGELOG.md` dated and accurate; known limitations honest
- [ ] No secrets in tracked files; `.env` ignored
- [ ] Tag + GitHub Release created; release marked `Latest`
