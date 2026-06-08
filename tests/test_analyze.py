"""Pure parse logic for the faithfulness self-check — no LLM, no DB."""

from surveyhelper.pipeline.analyze import _count_supported


def test_all_supported():
    assert _count_supported("1. SUPPORTED\n2. SUPPORTED\n3. SUPPORTED\n4. SUPPORTED") == 4


def test_partial_unsupported_not_miscounted():
    # "SUPPORTED" must not be counted inside "UNSUPPORTED"
    v = "1. SUPPORTED\n2. UNSUPPORTED: not in text\n3. SUPPORTED\n4. UNSUPPORTED: vague"
    assert _count_supported(v) == 2


def test_none_supported():
    assert _count_supported("1. UNSUPPORTED\n2. UNSUPPORTED\n3. UNSUPPORTED\n4. UNSUPPORTED") == 0


def test_capped_at_four():
    assert _count_supported("SUPPORTED " * 9) == 4
