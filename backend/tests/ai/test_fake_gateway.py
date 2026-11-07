"""LLM_MODE=fake trả đối tượng đúng schema (hợp đồng #3 – C1-02)."""

from app.ai.gateway import get_gateway
from app.models.schemas.session import Question


def test_fake_gateway_returns_valid_schema():
    q = get_gateway().call_json(Question, [{"role": "user", "content": "xin chào"}])
    assert isinstance(q, Question)


def test_fake_gateway_returns_valid_judge_result():
    from app.models.schemas.session import JudgeResult

    j = get_gateway().call_json(JudgeResult, [{"role": "user", "content": "chấm"}])
    assert len(j.criteria) == 5


def test_fake_embeddings_are_normalized_and_deterministic():
    import math

    from app.ai.providers.fake import FakeProvider

    vectors = FakeProvider().embed(["alpha beta", "beta alpha", "gamma delta"])
    assert len(vectors) == 3
    assert all(len(vector) == 768 for vector in vectors)
    assert all(math.isclose(sum(value * value for value in vector), 1.0) for vector in vectors)
    assert vectors[0] == vectors[1]
    assert vectors[0] != vectors[2]
    assert sum(a * b for a, b in zip(vectors[0], vectors[2], strict=True)) == 0.0
    assert FakeProvider().embed(["alpha beta"])[0] == vectors[0]


def test_fake_embedding_handles_empty_text_without_nan():
    from app.ai.providers.fake import FakeProvider

    assert FakeProvider().embed([""]) == [[0.0] * 768]
    assert FakeProvider().embed([]) == []
