"""Shared LLM types — the contract every backend (api / cli) returns."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Completion:
    text: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    model: str


class LLMError(RuntimeError):
    pass
