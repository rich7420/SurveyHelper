"""Local embeddings (Phase 6b). fastembed/onnx — no torch, no key, fully local.

bge-small-en-v1.5 is 384-dim, matching the pgvector columns. The model loads lazily
on first use (downloads ~130 MB once). Embedding runs off the event loop via a thread.
"""

from __future__ import annotations

import asyncio
import os

EMBED_DIM = 384
_MODEL_NAME = os.environ.get("SURVEYHELPER_EMBED_MODEL", "BAAI/bge-small-en-v1.5")
_model = None


def _get_model():
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        _model = TextEmbedding(model_name=_MODEL_NAME)
    return _model


def _embed_sync(texts: list[str]) -> list[list[float]]:
    model = _get_model()
    return [v.tolist() for v in model.embed(texts)]


async def embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    return await asyncio.to_thread(_embed_sync, texts)


async def embed_one(text: str) -> list[float]:
    return (await embed([text]))[0]


def to_pgvector(vec: list[float]) -> str:
    """Format a vector for a pgvector ::vector cast."""
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


def cosine(a: list[float], b: list[float]) -> float:
    import math
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0
