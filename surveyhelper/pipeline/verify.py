"""Synthesis contradiction verification (roadmap M2a → VISION §5, trust ladder L2+L4).

A *different* model than the synthesizer (cross-model, L1) checks whether each claimed
contradiction has clear **two-sided** evidence in the cited papers' content. If it does,
the claim is `verified` with the evidence; if not, it is downgraded to **`tentative`**
(abstention, L4) — a synthesis that says "I'm not sure" beats one confidently wrong.

Note: evidence is drawn from our *stored* content (tldr + structured deep fields), which
is itself grounded in the source. Full raw-source spans (true L2) await stored full text.
"""

from __future__ import annotations

import re
from typing import Any

from .. import config
from ..db import usage
from ..llm.claude_cli import complete
from ..logging_setup import get

log = get("verify")

_SYSTEM = ("You are a strict fact-checker. ONLY the provided paper content counts as evidence. "
           "Default to TENTATIVE whenever two-sided evidence is not clearly present.")


def parse_verdicts(text: str, n: int) -> dict[int, dict]:
    """Parse '<i>. VERIFIED: …' / '<i>. TENTATIVE: …' lines into {i: {status, note}}."""
    out: dict[int, dict] = {}
    # tolerate markdown/punctuation: "**1.**", "1)", "1 -", leading bold on the verdict
    for m in re.finditer(r"(?m)^\s*\**\s*(\d+)[.):\-]\s*\**\s*(VERIFIED|TENTATIVE)\b\**:?\s*(.*)$",
                         text, re.I):
        i = int(m.group(1))
        if 1 <= i <= n:
            out[i] = {"status": "verified" if m.group(2).upper() == "VERIFIED" else "tentative",
                      "note": m.group(3).strip()[:240]}
    return out


async def verify_contradictions(contradictions: list, content: dict[int, str], *,
                                job_id: int | None = None) -> tuple[list, int]:
    """Annotate each contradiction with status (verified|tentative) + evidence/why."""
    if not contradictions:
        return contradictions, 0

    blocks = []
    for i, c in enumerate(contradictions, 1):
        claim = c.get("claim") if isinstance(c, dict) else str(c)
        pids = c.get("papers", []) if isinstance(c, dict) else []
        srcs = "\n".join(f"    [{p}] {content.get(p, '(no stored content)')[:400]}" for p in pids)
        blocks.append(f"{i}. CLAIM: {claim}\n  CITED PAPERS:\n{srcs}")

    prompt = (
        "For each claimed contradiction, decide if the CITED PAPERS' content gives clear "
        "TWO-SIDED evidence (each paper supports its opposing side). Reply one line each:\n"
        "'<n>. VERIFIED: <the evidence from each side>' if both sides are clearly supported, or\n"
        "'<n>. TENTATIVE: <what two-sided evidence is missing>' otherwise. Be strict.\n\n"
        + "\n\n".join(blocks))
    c = await complete(prompt, model=config.VERIFY_MODEL, system=_SYSTEM)
    await usage.add(job_id=job_id, source="llm", calls=1,
                    tokens=c.input_tokens + c.output_tokens, cost_usd=c.cost_usd)

    verdicts = parse_verdicts(c.text, len(contradictions))
    annotated, n_verified = [], 0
    for i, con in enumerate(contradictions, 1):
        base = dict(con) if isinstance(con, dict) else {"claim": str(con), "papers": []}
        v = verdicts.get(i, {"status": "tentative", "note": "verifier did not assess"})
        base["status"] = v["status"]
        base["evidence"] = v["note"]
        if v["status"] == "verified":
            n_verified += 1
        annotated.append(base)
    log.info("verified %d/%d contradictions", n_verified, len(contradictions))
    return annotated, n_verified
