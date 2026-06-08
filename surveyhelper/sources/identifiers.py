"""Parse a free-form identifier into a typed Ref.

Handles: arXiv ids (new + old style, with/without version, 'arXiv:' prefix),
DOIs, Semantic Scholar ids, and URLs that embed any of these. Falls back to
treating the input as a title to search.
"""

from __future__ import annotations

import re

from ..models import Ref

# arXiv new style: 2310.01889 (optionally vN); old style: hep-th/9901001
_ARXIV_NEW = re.compile(r"\b(\d{4}\.\d{4,5})(v\d+)?\b")
_ARXIV_OLD = re.compile(r"\b([a-z\-]+(?:\.[A-Z]{2})?/\d{7})(v\d+)?\b")
_DOI = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", re.I)
_S2_HEX = re.compile(r"\b[0-9a-f]{40}\b")


def parse_identifier(text: str) -> Ref:
    s = text.strip()
    low = s.lower()

    # explicit Semantic Scholar id forms
    m = re.search(r"(?:semanticscholar\.org/paper/|s2:)([0-9a-f]{40})", low)
    if m:
        return Ref(kind="s2", value=m.group(1), raw=s)
    if _S2_HEX.fullmatch(low):
        return Ref(kind="s2", value=low, raw=s)

    has_arxiv_marker = "arxiv" in low
    cleaned = re.sub(r"arxiv:\s*", "", low)

    # DOI first when it's clearly a DOI (and not an arxiv-marked string)
    if not has_arxiv_marker:
        m = _DOI.search(s)
        if m:
            return Ref(kind="doi", value=m.group(0).rstrip(".").rstrip(")"), raw=s)

    # arXiv: accept if marked 'arxiv', a URL, or the whole string is a bare id
    m = _ARXIV_NEW.search(cleaned) or _ARXIV_OLD.search(cleaned)
    if m and (has_arxiv_marker or "arxiv.org" in low or _is_bare_arxiv(cleaned)):
        return Ref(kind="arxiv", value=m.group(1), raw=s)

    # DOI fallback (arxiv-marked but actually carries a DOI, unlikely)
    m = _DOI.search(s)
    if m:
        return Ref(kind="doi", value=m.group(0).rstrip(".").rstrip(")"), raw=s)

    return Ref(kind="title", value=s, raw=s)


def _is_bare_arxiv(s: str) -> bool:
    s = s.strip()
    return bool(re.fullmatch(r"(\d{4}\.\d{4,5})(v\d+)?", s)
                or re.fullmatch(r"([a-z\-]+(?:\.[A-Z]{2})?/\d{7})(v\d+)?", s))
