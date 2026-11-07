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
