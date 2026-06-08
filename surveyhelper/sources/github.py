"""GitHub code lookup (step 7). Papers with Code is dead (plan §2) -> GitHub URL
extraction from abstract/PDF, then verify the repo exists via the API."""

from __future__ import annotations

from .. import config, http
from ..models import CodeInfo

_API = "https://api.github.com/repos"


def _headers() -> dict[str, str]:
    h = {"Accept": "application/vnd.github+json"}
    if config.GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {config.GITHUB_TOKEN}"
    return h


async def find_code(github_urls: list[str]) -> CodeInfo:
    """Given candidate GitHub URLs, return the first that verifies as a real repo."""
    for url in github_urls:
        tail = url.split("github.com/", 1)[-1].rstrip("/")
        parts = tail.split("/")
        if len(parts) < 2:
            continue
        owner_repo = f"{parts[0]}/{parts[1]}"
        if owner_repo.endswith(".git"):
            owner_repo = owner_repo[:-4]
        resp = await http.request("github", "GET", f"{_API}/{owner_repo}", headers=_headers())
        if resp.status_code != 200:
            continue
        d = resp.json()
        return CodeInfo(
            found=True, repo=owner_repo, url=d.get("html_url"),
            stars=d.get("stargazers_count"), archived=d.get("archived"),
        )
    return CodeInfo(found=False)
