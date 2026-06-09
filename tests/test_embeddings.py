"""Embedding helpers — pure logic (cosine, pgvector format), no model load."""

from surveyhelper.embeddings import cosine, to_pgvector


def test_cosine_identical_is_one():
    assert abs(cosine([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) - 1.0) < 1e-9


def test_cosine_orthogonal_is_zero():
    assert abs(cosine([1.0, 0.0], [0.0, 1.0])) < 1e-9


def test_cosine_ordering():
    q = [1.0, 1.0, 0.0]
    near = [1.0, 0.9, 0.0]
    far = [0.0, 0.1, 1.0]
    assert cosine(q, near) > cosine(q, far)


def test_cosine_zero_vector_safe():
    assert cosine([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_to_pgvector_format():
    assert to_pgvector([0.5, -1.0, 2.0]) == "[0.500000,-1.000000,2.000000]"
