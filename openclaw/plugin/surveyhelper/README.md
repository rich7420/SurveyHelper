# surveyHelper — OpenClaw ambient recognition

An [OpenClaw](https://github.com/openclaw/openclaw) plugin that makes
[surveyHelper](https://github.com/rich7420/SurveyHelper) **ambient**: on each turn it cheaply checks
whether you mentioned a paper that's already in your local research graph (via surveyHelper's
`/recognize` — local DB, no LLM), and if so injects what you know about it into the prompt — so the
agent is aware with **no tool call**. Shallow in-graph papers get quietly deepened in the background.

## Requires
A running surveyHelper MCP server (default `http://host.docker.internal:8765`) — see the
[surveyHelper README](https://github.com/rich7420/SurveyHelper).

## Install
```bash
# from ClawHub (once published)
openclaw plugins install clawhub:openclaw-surveyhelper

# or from a clone of the surveyHelper repo
bash openclaw/plugin/install-plugin.sh
```

## Config
`endpoint` (optional) — the surveyHelper HTTP base URL. Defaults to `http://host.docker.internal:8765`.

MIT licensed.
