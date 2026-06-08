"""Identifier parsing — pure logic, no network."""

from surveyhelper.sources.identifiers import parse_identifier


def test_bare_arxiv_new():
    r = parse_identifier("2310.01889")
    assert r.kind == "arxiv" and r.value == "2310.01889"


def test_arxiv_with_prefix_and_version():
    r = parse_identifier("arXiv:2310.01889v2")
    assert r.kind == "arxiv" and r.value == "2310.01889"


def test_arxiv_url():
    r = parse_identifier("https://arxiv.org/abs/2310.01889")
    assert r.kind == "arxiv" and r.value == "2310.01889"


def test_arxiv_old_style():
    r = parse_identifier("arXiv:hep-th/9901001")
    assert r.kind == "arxiv" and r.value == "hep-th/9901001"


def test_doi():
    r = parse_identifier("10.1145/3292500.3330701")
    assert r.kind == "doi" and r.value == "10.1145/3292500.3330701"


def test_doi_url():
    r = parse_identifier("https://doi.org/10.1038/s41586-021-03819-2")
    assert r.kind == "doi" and r.value.startswith("10.1038/")


def test_s2_hex():
    r = parse_identifier("0" * 40)
    assert r.kind == "s2"


def test_title_fallback():
    r = parse_identifier("Attention Is All You Need")
    assert r.kind == "title" and r.value == "Attention Is All You Need"


def test_aliases_dedup_keys():
    from surveyhelper.models import PaperMeta
    m = PaperMeta(arxiv_id="2310.01889", s2_id="abc", doi="10.1/X")
    assert m.aliases() == ["arxiv:2310.01889", "s2:abc", "doi:10.1/x"]
