"""OpenAI + Gemini adapters: tier mapping + cost math (pure, no network)."""

from surveyhelper import config
from surveyhelper.llm import gemini_api, openai_api


class _Obj:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


# ── tier mapping: the pipeline's Claude model → provider tier ────────────────
def test_openai_tier_mapping():
    assert openai_api._model("claude-haiku-4-5") == config.OPENAI_SUMMARY_MODEL
    assert openai_api._model("claude-sonnet-4-6") == config.OPENAI_MODEL
    assert openai_api._model(None) == config.OPENAI_SUMMARY_MODEL


def test_gemini_tier_mapping():
    assert gemini_api._model("claude-haiku-4-5") == config.GEMINI_SUMMARY_MODEL
    assert gemini_api._model("claude-opus-4-8") == config.GEMINI_MODEL


# ── cost math, including the cached-token discount ───────────────────────────
def test_openai_cost_with_cache():
    u = _Obj(prompt_tokens=1_000_000, completion_tokens=0,
             prompt_tokens_details=_Obj(cached_tokens=1_000_000))
    pin, pout, cost = openai_api._cost("gpt-5.4-mini", u)
    assert pin == 1_000_000 and pout == 0
    assert abs(cost - 0.75 * 0.1) < 1e-9          # all-cached input bills at ~0.1x


def test_openai_cost_plain():
    u = _Obj(prompt_tokens=0, completion_tokens=1_000_000, prompt_tokens_details=None)
    _, _, cost = openai_api._cost("gpt-5.4", u)
    assert abs(cost - 15.0) < 1e-9                 # gpt-5.4 output $15/1M


def test_gemini_cost_with_cache():
    um = _Obj(prompt_token_count=1_000_000, candidates_token_count=0,
              cached_content_token_count=1_000_000)
    pin, pout, cost = gemini_api._cost("gemini-3.5-flash", um)
    assert pin == 1_000_000
    assert abs(cost - 0.30 * 0.25) < 1e-9          # all-cached input bills at 0.25x


def test_unknown_model_uses_default_price():
    _, _, cost = openai_api._cost("future-model", _Obj(prompt_tokens=1_000_000,
                                                       completion_tokens=0, prompt_tokens_details=None))
    assert cost > 0                                # falls back, never free
