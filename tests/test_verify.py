"""Contradiction-verdict parsing — pure logic, no LLM (M2a)."""

from surveyhelper.pipeline.verify import parse_verdicts


def test_parses_verified_and_tentative():
    t = ("1. VERIFIED: BERT fine-tunes the model; ELMo uses fixed features\n"
         "2. TENTATIVE: only one paper's side is evidenced\n"
         "3. VERIFIED: both sides clear")
    v = parse_verdicts(t, 3)
    assert v[1]["status"] == "verified"
    assert v[2]["status"] == "tentative"
    assert v[3]["status"] == "verified"
    assert "fixed features" in v[1]["note"]


def test_out_of_range_ignored():
    assert parse_verdicts("5. VERIFIED: x", 3) == {}


def test_unparseable_yields_nothing():
    assert parse_verdicts("no verdicts here", 2) == {}


def test_case_insensitive():
    assert parse_verdicts("1. tentative: meh", 1)[1]["status"] == "tentative"
