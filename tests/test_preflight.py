"""Preflight pure logic: DSN redaction + backend↔key check (no network/DB)."""

from surveyhelper import preflight


def test_safe_dsn_hides_password(monkeypatch):
    monkeypatch.setattr(preflight.config, "DSN", "postgresql://user:secret@host:5544/db")
    assert preflight._safe_dsn() == "postgresql://user:***@host:5544/db"


def test_key_problem_flags_missing(monkeypatch):
    monkeypatch.setattr(preflight, "BACKEND", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert "OPENAI_API_KEY" in (preflight.llm_key_problem() or "")


def test_key_problem_none_when_set(monkeypatch):
    monkeypatch.setattr(preflight, "BACKEND", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    assert preflight.llm_key_problem() is None


def test_key_problem_none_for_cli(monkeypatch):
    monkeypatch.setattr(preflight, "BACKEND", "cli")
    assert preflight.llm_key_problem() is None
