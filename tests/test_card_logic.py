"""Pure card/worker logic — no DB, no network."""

from surveyhelper.pipeline.card import _status_for_step1, _step1_ladder
from surveyhelper.worker import MAX_ENRICH_ATTEMPTS, _backoff_seconds


def test_step1_prefers_tldr():
    text, src = _step1_ladder("a crisp tldr.", "long abstract here. second sentence.")
    assert src == "tldr" and text == "a crisp tldr."


def test_step1_falls_back_to_abstract_first_two_sentences():
    text, src = _step1_ladder(None, "First sentence. Second sentence. Third sentence.")
    assert src == "abstract_extractive"
    assert text == "First sentence. Second sentence."
    assert "Third" not in text


def test_step1_none_when_no_tldr_no_abstract():
    text, src = _step1_ladder(None, None)
    assert src == "none" and text is None


def test_step1_status_mapping():
    assert _status_for_step1("tldr") == "ok"
    assert _status_for_step1("abstract_extractive") == "partial"
    assert _status_for_step1("none") == "skipped"


def test_backoff_is_capped_and_monotonic():
    vals = [_backoff_seconds(i) for i in range(MAX_ENRICH_ATTEMPTS)]
    assert vals[0] == 60                  # 1 min first retry
    assert all(b <= 30 * 60 for b in vals)  # capped at 30 min
    assert vals == sorted(vals)           # non-decreasing
