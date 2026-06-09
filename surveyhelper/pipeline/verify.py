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
from ..fulltext import get_fulltext
from ..llm.claude_cli import complete
from ..logging_setup import get

log = get("verify")

_SYSTEM = ("You are a strict fact-checker. ONLY the provided paper content counts as evidence. "
           "Default to TENTATIVE whenever two-sided evidence is not clearly present.")

_SYSTEM_GROUNDED = (
    "You are a strict fact-checker reading FULL paper texts. A claimed contradiction is VERIFIED "
    "only if you can COPY a contiguous span of at least 10 words EXACTLY (verbatim, character for "
    "character) from EACH cited paper supporting its opposing side. Do NOT paraphrase, summarize, "
    "reconstruct, or stitch phrases together — copy a real run of words exactly as it appears. If "
    "no such verbatim span exists in a paper, the claim is TENTATIVE.")

MAX_GROUNDED = 6          # cap contradictions verified against full text (cost/latency)
MAX_TEXT_CHARS = 40_000   # per paper, into the verifier prompt


def _parse_grounded(text: str) -> tuple[str, str]:
    m = re.match(r"\s*\**\s*(VERIFIED|TENTATIVE)\b\**:?\s*(.*)", text.strip(), re.I | re.S)
    if m:
        return ("verified" if m.group(1).upper() == "VERIFIED" else "tentative",
                m.group(2).strip())
    return ("tentative", text.strip()[:200])   # unparseable -> abstain


# A cited quote looks like:  [131] "verbatim sentence from the paper"
_QUOTE_RE = re.compile(r"\[(\d+)\]\s*[\"“”']([^\"“”']{8,})[\"“”']")


def _extract_quotes(text: str) -> list[tuple[int, str]]:
    return [(int(m.group(1)), m.group(2)) for m in _QUOTE_RE.finditer(text)]


def _norm(s: str) -> str:
    """Lowercase, drop punctuation, collapse whitespace — robust to PDF/HTML extraction noise."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s.lower())).strip()


def _quote_in_text(quote: str, norm_text: str, *, min_run: int = 8) -> bool:
    """True iff the quote is verbatim in the source: the whole normalized quote is a substring,
    OR a contiguous run of >= `min_run` of its words is. The run tolerates a mangled word at the
    edges (PDF/HTML extraction noise) but still rejects paraphrase — a reworded sentence has no
    long verbatim run. This makes 'verified' a *mechanical* fact, not the verifier's say-so."""
    nq = _norm(quote)
    if len(nq) < 24:
        return False
    if nq in norm_text:
        return True
    toks = nq.split()
    if len(toks) < min_run:
        return False
    return any(" ".join(toks[i:i + min_run]) in norm_text
              for i in range(len(toks) - min_run + 1))


async def verify_contradictions_grounded(contradictions: list, arxiv_map: dict[int, str], *,
                                         job_id: int | None = None) -> tuple[list, int]:
    """L2: verify each contradiction against the cited papers' FULL TEXT (fetched on demand).
    VERIFIED only with a real quoted span from each side; else TENTATIVE (abstain)."""
    if not contradictions:
        return contradictions, 0

    # fetch full text once per unique cited paper that has an arXiv id
    cited = {p for c in contradictions if isinstance(c, dict) for p in c.get("papers", [])}
    texts: dict[int, str] = {}
    for pid in cited:
        aid = arxiv_map.get(pid)
        if not aid:
            continue
        try:
            t = await get_fulltext(pid, aid, max_chars=MAX_TEXT_CHARS)   # cached
            if t:
                texts[pid] = t
        except Exception as exc:
            log.warning("verify: full text fetch failed for %s (%s)", pid, exc)
    norm_texts = {pid: _norm(t) for pid, t in texts.items()}   # for mechanical quote matching

    annotated, n_verified, n_grounded = [], 0, 0
    for c in contradictions:
        base = dict(c) if isinstance(c, dict) else {"claim": str(c), "papers": []}
        pids = base.get("papers", [])
        have = [p for p in pids if p in texts]
        if len(have) < 2 or n_grounded >= MAX_GROUNDED:
            base["status"] = "tentative"
            base["evidence"] = (f"full text unavailable for {len(pids) - len(have)} cited paper(s)"
                                if len(have) < 2 else "not checked (cap reached)")
            annotated.append(base)
            continue

        n_grounded += 1
        blocks = "\n\n".join(f"=== PAPER [{p}] FULL TEXT ===\n{texts[p]}" for p in have[:2])
        prompt = (f"CLAIMED CONTRADICTION: {base.get('claim')}\n\n{blocks}\n\n"
                  "Does each cited paper's text actually support its side of this contradiction? "
                  "Quote the EXACT sentence from each that does. Reply ONE of:\n"
                  "'VERIFIED: [<id>] \"<verbatim quote>\"; [<id>] \"<verbatim quote>\"'  (both sides real), or\n"
                  "'TENTATIVE: <which side has no supporting sentence>'.")
        r = await complete(prompt, model=config.VERIFY_MODEL, system=_SYSTEM_GROUNDED)
        await usage.add(job_id=job_id, source="llm", calls=1,
                        tokens=r.input_tokens + r.output_tokens, cost_usd=r.cost_usd)
        status, evidence = _parse_grounded(r.text)
        base["grounding"] = "full_text"

        # The crux: don't trust the verifier's say-so. If it claims VERIFIED, mechanically
        # confirm its quotes are verbatim in the source, from two distinct papers. Else abstain.
        if status == "verified":
            quotes = _extract_quotes(r.text)
            papers_quoted = {p for p, _ in quotes}
            verbatim = bool(quotes) and all(_quote_in_text(q, norm_texts.get(p, "")) for p, q in quotes)
            if verbatim and len(papers_quoted) >= 2:
                base["grounding"] = "full_text+verbatim"
                base["evidence"] = evidence[:400]
            else:
                status = "tentative"
                base["evidence"] = "verifier quote(s) not found verbatim in the source — abstaining"
        else:
            base["evidence"] = evidence[:400]

        base["status"] = status
        if status == "verified":
            n_verified += 1
        annotated.append(base)

    log.info("grounded-verified %d/%d contradictions (%d checked against full text)",
             n_verified, len(contradictions), n_grounded)
    return annotated, n_verified


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
