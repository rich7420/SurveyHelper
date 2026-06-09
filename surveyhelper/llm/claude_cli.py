"""`claude -p` completion adapter (Phase 2 LLM routing).

Reuses the OpenClaw container's authenticated Claude **subscription** via
`docker exec <container> claude -p --output-format json`. The prompt is piped on
stdin (papers are large); tools are disabled (the paper text is untrusted — treat it
as data, never instructions; DECISIONS §I). Returns the text plus per-call token
usage and cost (fed to `usage_log`).

Note: `claude -p` runs the Claude Code agent (a cached ~13k-token system prompt rides
each call), so it is slower and pricier than a bare model API — acceptable for a
background analyze job; revisit with an API key if volume grows.
"""

from __future__ import annotations

import asyncio
import json

from .. import config
from ..logging_setup import get
from .base import Completion, LLMError

log = get("llm")

# No tools: the worker only ever wants a completion over (untrusted) paper text.
_DISALLOWED = "Bash Read Edit Write WebSearch WebFetch Glob Grep NotebookEdit Task"


async def complete(prompt: str, *, model: str | None = None, system: str | None = None,
                   timeout: float = 180.0, cache_context: str | None = None) -> Completion:
    model = model or config.LLM_SUMMARY_MODEL
    if cache_context:   # no API-level cache here; just prepend the shared block
        prompt = f"{cache_context}\n\n{prompt}"
    args = [
        "docker", "exec", "-i", config.LLM_CONTAINER,
        "claude", "-p", "--output-format", "json",
        "--model", model, "--disallowedTools", _DISALLOWED,
    ]
    if system:
        args += ["--append-system-prompt", system]

    proc = await asyncio.create_subprocess_exec(
        *args, stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(prompt.encode()), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise LLMError(f"claude -p timed out after {timeout}s")

    if proc.returncode != 0:
        raise LLMError(f"claude -p exited {proc.returncode}: {err.decode()[:300]}")
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        raise LLMError(f"claude -p non-JSON output: {out.decode()[:300]}")
    if data.get("is_error"):
        raise LLMError(f"claude -p error: {data.get('result')!r}")

    usage = data.get("usage") or {}
    return Completion(
        text=data.get("result", ""),
        input_tokens=int(usage.get("input_tokens", 0)),
        output_tokens=int(usage.get("output_tokens", 0)),
        cost_usd=float(data.get("total_cost_usd", 0.0)),
        model=model,
    )
