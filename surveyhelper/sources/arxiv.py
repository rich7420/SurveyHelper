"""arXiv API client (metadata + PDF url). Paced 1 req/4s, single-flight (§9)."""

from __future__ import annotations

import re
from typing import Optional

import feedparser

from .. import http
from ..models import PaperMeta

_BASE = "http://export.arxiv.org/api/query"
_GH = re.compile(r"https?://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
# References in arXiv HTML appear as "arXiv:2310.01889" text and/or .../abs/ links.
_ARXIV_REF = re.compile(r"(?:arxiv\.org/(?:abs|html|pdf)/|arxiv:)(\d{4}\.\d{4,5})", re.I)


def _entry_to_meta(e, fallback_id: str = "") -> Optional[PaperMeta]:
    if getattr(e, "title", None) is None:
        return None
    eid = getattr(e, "id", "") or ""
    m = re.search(r"abs/([^v\s]+)(v\d+)?", eid)
    canonical = m.group(1) if m else fallback_id

    pdf_url = None
    for link in getattr(e, "links", []):
        if getattr(link, "type", "") == "application/pdf":
            pdf_url = link.href
    if pdf_url is None:
        pdf_url = f"https://arxiv.org/pdf/{canonical}"

    authors = [a.name for a in getattr(e, "authors", [])] if hasattr(e, "authors") else []
    year = None
    if getattr(e, "published", None):
        ym = re.match(r"(\d{4})", e.published)
        year = int(ym.group(1)) if ym else None

    summary = re.sub(r"\s+", " ", getattr(e, "summary", "") or "").strip()
    return PaperMeta(
        arxiv_id=canonical,
        title=re.sub(r"\s+", " ", e.title).strip(),
        authors=authors, year=year, abstract=summary,
        doi=getattr(e, "arxiv_doi", None),
        url=f"https://arxiv.org/abs/{canonical}",
        pdf_url=pdf_url, venue="arXiv", text_coverage="full",
        github_urls=sorted(set(_GH.findall(summary))),
    )


async def fetch_metadata(arxiv_id: str) -> Optional[PaperMeta]:
    """Return normalized metadata for an arXiv id, or None if not found."""
    text = await http.get_text("arxiv", _BASE, params={"id_list": arxiv_id, "max_results": "1"})
    feed = feedparser.parse(text)
    if not feed.entries:
        return None
    return _entry_to_meta(feed.entries[0], fallback_id=arxiv_id)


async def search_recent(query: str, *, max_results: int = 20, since=None) -> list[PaperMeta]:
    """Recent papers matching a free-text query, newest first (proactive scan, §8).

    If `since` (a tz-aware datetime) is given, only papers submitted after it are kept.
    """
    import calendar
    import datetime as _dt

    text = await http.get_text("arxiv", _BASE, params={
        "search_query": f"all:{query}", "sortBy": "submittedDate",
        "sortOrder": "descending", "max_results": str(max_results)})
    feed = feedparser.parse(text)
    out: list[PaperMeta] = []
    for e in feed.entries:
        if since is not None and getattr(e, "published_parsed", None):
            pub = _dt.datetime.fromtimestamp(calendar.timegm(e.published_parsed), _dt.timezone.utc)
            if pub <= since:
                continue
        meta = _entry_to_meta(e)
        if meta and meta.arxiv_id:
            out.append(meta)
    return out


_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


async def fetch_fulltext(arxiv_id: str, *, max_chars: int = 120_000) -> Optional[str]:
    """Plain-text paper body for whole-paper LLM analysis: arXiv HTML, else the PDF
    (pymupdf) for pre-HTML papers, else None. Truncated to `max_chars`."""
    resp = await http.request("arxiv", "GET", f"https://arxiv.org/html/{arxiv_id}")
    if resp.status_code == 200:
        html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", resp.text, flags=re.S | re.I)
        text = _WS.sub(" ", _TAG.sub(" ", html)).strip()
        if text:
            return text[:max_chars]
    return await _pdf_fulltext(arxiv_id, max_chars)


async def _pdf_fulltext(arxiv_id: str, max_chars: int) -> Optional[str]:
    resp = await http.request("arxiv", "GET", f"https://arxiv.org/pdf/{arxiv_id}")
    if resp.status_code != 200:
        return None
    import fitz  # pymupdf
    try:
        with fitz.open(stream=resp.content, filetype="pdf") as doc:
            text = _WS.sub(" ", " ".join(page.get_text() for page in doc)).strip()
    except Exception:
        return None
    return text[:max_chars] or None


async def fetch_html_references(arxiv_id: str) -> list[str]:
    """Keyless reference fallback (DECISIONS: cut the hard S2 dependency).

    Parse the arXiv HTML rendering's bibliography for *referenced arXiv ids*. Only
    papers with an HTML rendering (LaTeX source, ~Dec 2023+) and arXiv-linked
    citations yield results — best-effort, degrades to [] otherwise. Returns the
    cited arXiv ids (self excluded), which our arXiv resolver can canonicalize.
    """
    resp = await http.request("arxiv", "GET", f"https://arxiv.org/html/{arxiv_id}")
    if resp.status_code != 200:
        return []
    ids = {m for m in _ARXIV_REF.findall(resp.text)}
    ids.discard(arxiv_id)
    ids.discard(arxiv_id.split("v")[0])
    return sorted(ids)
