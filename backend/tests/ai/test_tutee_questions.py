"""C1-04 – Sinh 3–5 câu hỏi phản biện theo 4 chiến lược (6.2.4, Hình 6.6) từ rubric và lời giảng.

Xong khi: với lời giảng còn thiếu ý, câu hỏi nhắm đúng ý còn thiếu trong rubric.
"""

import pytest

from app.ai.agents.guard import GuardAgent
from app.ai.agents.tutee import (
    CoverageAnalysis,
    SessionContext,
    TuteeAgent,
    choose_strategy,
    fallback_question,
    role_violation,
)
from app.ai.gateway import build_gateway
from app.core.config import Settings
from app.models.enums import QuestionStrategy as S
from app.models.schemas.session import Question
from app.services.skill_tree import load_seed_tree

N5 = next(n for n in load_seed_tree().nodes if n.code == "N5")  # Con trỏ – có rubric đầy đủ (Bảng 6.1)
EXPLANATION = (
    "Con trỏ là một biến đặc biệt, nó lưu địa chỉ của một ô nhớ khác. Dùng & để lấy địa chỉ, * để đọc giá trị."
)
TRANSCRIPT = [{"role": "student", "text": EXPLANATION}]


class ScriptedGateway:
    def __init__(self, outputs=()):
        self.outputs = list(outputs)
        self.calls: list[dict] = []

    def call_json(self, schema, messages, **kw):
        self.calls.append({"schema": schema, "messages": messages, **kw})
        return schema.model_validate(self.outputs.pop(0))


def _tutee(outputs=(), **kw):
    gw = ScriptedGateway(outputs)
    guard = GuardAgent(gw, model="guard-mini", use_llm_output_check=False)
    return TuteeAgent(gw, guard=guard, **kw), gw


def cov(covered=("KP1", "KP2", "KP3"), detected=(), corrected=()) -> CoverageAnalysis:
    return CoverageAnalysis(
        covered_points=list(covered),
        missing_points=[k for k in ("KP1", "KP2", "KP3") if k not in covered],
        detected_misconceptions=list(detected),
        corrected_misconceptions=list(corrected),
    )


def ctx(coverage, asked=(), max_questions=4) -> SessionContext:
    return SessionContext(
        node=N5, transcript=TRANSCRIPT, coverage=coverage, asked=list(asked), max_questions=max_questions
    )


def asked_q(strategy, target):
    return Question(text="câu đã hỏi?", strategy=strategy, target_point_id=target)


# --- chọn chiến lược theo Hình 6.6 -------------------------------------------------------------


def test_missing_required_point_first():
    assert choose_strategy(ctx(cov(covered=("KP1", "KP2")))) == (S.MISSING_KEY_POINT, "KP3")


def test_misconception_probe_when_all_points_covered():
    assert choose_strategy(ctx(cov(detected=["MC2"]))) == (S.MISCONCEPTION_PROBE, "MC2")


def test_corrected_misconception_not_probed_again():
    c = ctx(cov(detected=["MC2"], corrected=["MC2"]))
    assert choose_strategy(c) == (S.EDGE_CASE, "SC1")


def test_edge_case_then_transfer():
    used = [asked_q(S.EDGE_CASE, sc) for sc in ("SC1", "SC2", "SC3")]
    assert choose_strategy(ctx(cov(), asked=used[:1])) == (S.EDGE_CASE, "SC2")
    assert choose_strategy(ctx(cov(), asked=used, max_questions=5)) == (S.TRANSFER, None)


def test_does_not_repeat_same_target():
    c = ctx(cov(covered=("KP1",)), asked=[asked_q(S.MISSING_KEY_POINT, "KP2")])
    assert choose_strategy(c) == (S.MISSING_KEY_POINT, "KP3")


def test_stops_at_max_questions():
    asked = [asked_q(S.EDGE_CASE, f"SC{i}") for i in (1, 2, 3)]
    assert choose_strategy(ctx(cov(covered=("KP1",)), asked=asked, max_questions=3)) is None


def test_max_questions_clamped_to_3_5():
    assert ctx(cov(), max_questions=10).max_questions == 5
    assert ctx(cov(), max_questions=1).max_questions == 3


def test_stops_early_when_nothing_left_after_min_questions():
    used = [asked_q(S.EDGE_CASE, sc) for sc in ("SC1", "SC2", "SC3")] + [asked_q(S.TRANSFER, None)]
    assert choose_strategy(ctx(cov(), asked=used, max_questions=5)) is None


def test_at_least_three_questions_even_when_rubric_is_thin():
    thin = N5.model_copy(update={"rubric": N5.rubric.model_copy(update={"scenarios": [], "misconceptions": []})})
    c = SessionContext(node=thin, transcript=TRANSCRIPT, coverage=cov(), asked=[asked_q(S.TRANSFER, None)])
    assert choose_strategy(c) is not None  # mới 1 câu ⇒ vẫn hỏi tiếp cho đủ 3


# --- phân tích bao phủ ------------------------------------------------------------------------


def test_analyze_coverage_normalises_to_rubric_and_wraps_transcript():
    tutee, gw = _tutee(
        [{"coveredPoints": ["KP1", "KP2", "KP9"], "missingPoints": [], "detectedMisconceptions": ["MC2", "MCx"]}]
    )
    c = tutee.analyze_coverage(TRANSCRIPT, N5, session_id="s1")
    assert c.covered_points == ["KP1", "KP2"] and c.missing_points == ["KP3"]
    assert c.detected_misconceptions == ["MC2"]
    call = gw.calls[0]
    assert call["temperature"] == 0 and call["session_id"] == "s1"
    assert "<student_transcript>" in call["messages"][-1]["content"]
    assert "KP3" in call["messages"][0]["content"]


# --- Xong khi: lời giảng thiếu ý ⇒ câu hỏi nhắm đúng ý thiếu ---------------------------------


def test_missing_point_question_targets_missing_key_point():
    q_text = "Vậy con trỏ có biết nó đang trỏ vào kiểu dữ liệu gì không, hay địa chỉ nào cũng như nhau hả bạn?"
    tutee, gw = _tutee(
        [
            {"coveredPoints": ["KP1", "KP2"], "missingPoints": ["KP3"], "detectedMisconceptions": []},
            {"question": q_text, "targetPointId": "KP1", "strategy": "EDGE_CASE"},  # LLM ghi sai ⇒ bị ghi đè
        ]
    )
    c = SessionContext(node=N5, transcript=TRANSCRIPT, coverage=tutee.analyze_coverage(TRANSCRIPT, N5))
    q = tutee.next_question(c)
    assert q.text == q_text
    assert q.strategy == S.MISSING_KEY_POINT and q.target_point_id == "KP3"
    system = gw.calls[1]["messages"][0]["content"]
    assert "MISSING_KEY_POINT" in system and "KP3" in system
    assert "<student_transcript>" in gw.calls[1]["messages"][-1]["content"]


def test_leaking_question_regenerated_then_bank_fallback():
    leak = {
        "question": "Có phải con trỏ có kiểu, kiểu quyết định cách đọc ô nhớ và bước nhảy khi cộng con trỏ không bạn?"
    }
    tutee, gw = _tutee([leak, leak, leak])
    q = tutee.next_question(ctx(cov(covered=("KP1", "KP2"))))
    assert len(gw.calls) == 3
    assert q == fallback_question(N5, S.MISSING_KEY_POINT, "KP3")
    assert q.target_point_id == "KP3" and role_violation(q.text, N5.title) is None


def test_misconception_fallback_uses_probe_question():
    q = fallback_question(N5, S.MISCONCEPTION_PROBE, "MC2")
    assert q.text == N5.rubric.misconceptions[1].probe_question


@pytest.mark.parametrize("strategy,target", [(S.MISSING_KEY_POINT, "KP3"), (S.EDGE_CASE, "SC2"), (S.TRANSFER, None)])
def test_bank_fallbacks_stay_in_role_and_do_not_leak(strategy, target):
    q = fallback_question(N5, strategy, target)
    assert role_violation(q.text, N5.title) is None
    kp3 = N5.rubric.key_points[2].content
    assert kp3 not in q.text


def test_returns_none_when_round_is_over():
    tutee, gw = _tutee()
    asked = [asked_q(S.EDGE_CASE, f"SC{i}") for i in (1, 2, 3)]
    assert tutee.next_question(ctx(cov(), asked=asked, max_questions=3)) is None
    assert gw.calls == []


# --- trọn một vòng phản biện: 3–5 câu ----------------------------------------------------------


def test_full_round_asks_between_3_and_5_questions():
    outputs = [{"question": f"Nếu tình huống {i} thì sao hả bạn?"} for i in range(10)]
    tutee, _ = _tutee(outputs, max_questions=5)
    c = ctx(cov(covered=("KP1", "KP2")), max_questions=5)
    while (q := tutee.next_question(c)) is not None:
        c.asked.append(q)
    assert 3 <= len(c.asked) <= 5
    assert c.asked[0].strategy == S.MISSING_KEY_POINT and c.asked[0].target_point_id == "KP3"
    assert len({(q.strategy, q.target_point_id) for q in c.asked}) == len(c.asked)  # không lặp


def test_fake_mode_question_in_role():
    gw = build_gateway(Settings(llm_mode="fake"))
    tutee = TuteeAgent(gw)
    q = tutee.next_question(
        SessionContext(node=N5, transcript=TRANSCRIPT, coverage=tutee.analyze_coverage(EXPLANATION, N5))
    )
    assert q is not None and role_violation(q.text, N5.title) is None


def test_bank_fallback_that_leaks_is_replaced_by_generic_question():
    """Câu trong ngân hàng (người soạn rubric viết) lỡ chứa ý chính ⇒ không dùng."""
    kp3 = N5.rubric.key_points[2].content
    bad_mc = N5.rubric.misconceptions[0].model_copy(update={"id": "MCX", "probe_question": kp3 + " đúng không?"})
    leaky = N5.model_copy(update={"rubric": N5.rubric.model_copy(update={"misconceptions": [bad_mc]})})
    q = fallback_question(leaky, S.MISCONCEPTION_PROBE, "MCX")
    assert kp3 not in q.text and role_violation(q.text, N5.title) is None
