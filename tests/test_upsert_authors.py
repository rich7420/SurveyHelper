"""Regression: an empty incoming field (reference-stub / enrich) must not clobber stored
metadata (authors, abstract) that a survey already fetched."""

import pytest

from surveyhelper.db import get_pool
from surveyhelper.db import papers as papers_db
from surveyhelper.models import PaperMeta

AID = "9999.00042"


async def _db():
    try:
        return await get_pool()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"DB unavailable: {exc}")


@pytest.mark.asyncio
async def test_empty_upsert_preserves_authors_and_abstract():
    pool = await _db()
    await pool.execute("DELETE FROM papers WHERE arxiv_id=$1", AID)

    await papers_db.upsert(PaperMeta(arxiv_id=AID, title="A Sufficiently Long Test Title",
                                     authors=["Ada Lovelace", "Grace Hopper"],
                                     abstract="The real abstract."))
    # reference-stub / enrich style re-upserts with the fields empty
    await papers_db.upsert(PaperMeta(arxiv_id=AID, title="A Sufficiently Long Test Title",
                                     authors=[], abstract=""))

    authors = await pool.fetchval("SELECT authors FROM papers WHERE arxiv_id=$1", AID)
    abstract = await pool.fetchval("SELECT abstract FROM papers WHERE arxiv_id=$1", AID)
    assert authors == ["Ada Lovelace", "Grace Hopper"]   # not wiped to []
    assert abstract == "The real abstract."              # not wiped to ""

    await pool.execute("DELETE FROM papers WHERE arxiv_id=$1", AID)
