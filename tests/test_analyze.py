"""Pure parse logic for analyze — faithfulness count + structured JSON extraction."""

from surveyhelper.pipeline.analyze import _count_supported, _extract_json


def test_extract_json_plain():
    assert _extract_json('{"a": 1, "b": ["x"]}') == {"a": 1, "b": ["x"]}


def test_extract_json_fenced():
    assert _extract_json('```json\n{"core_idea": "x"}\n```') == {"core_idea": "x"}


def test_extract_json_embedded_in_prose():
    assert _extract_json('Sure: {"k": [1, 2]} — done.') == {"k": [1, 2]}


def test_extract_json_invalid_returns_none():
    assert _extract_json("no json at all") is None
    assert _extract_json('{"broken": ') is None


def test_extract_json_non_object_returns_none():
    assert _extract_json("[1, 2, 3]") is None


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
