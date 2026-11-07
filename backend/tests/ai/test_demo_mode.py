"""C1-13 – DEMO_MODE=1: LLM mất kết nối thì Tutee, độ bao phủ và Judge chuyển sang nội dung lưu sẵn;
tắt demo thì lỗi nổi lên."""

import pytest

from app.ai import demo
from app.ai.agents.judge import JudgeAgent
from app.ai.agents.tutee import CoverageAnalysis, SessionContext, TuteeAgent, opening_template
from app.core.config import get_settings
from app.core.errors import AppError
from app.models.enums import Verdict
from app.services.skill_tree import load_seed_tree

NODE = next(n for n in load_seed_tree().nodes if n.key == "n5_con_tro")
RUBRIC = NODE.rubric


class DeadGateway:
    """LLM mất kết nối: mọi lời gọi đều 503 LLM_UNAVAILABLE (đã hết model dự phòng)."""

    def __init__(self):
        self.calls = 0

    def call_json(self, *a, **kw):
        self.calls += 1
        raise AppError(503, "LLM_UNAVAILABLE", "Dịch vụ AI tạm thời không khả dụng")

    def embed(self, texts):
        raise AppError(503, "LLM_UNAVAILABLE", "Dịch vụ AI tạm thời không khả dụng")


@pytest.fixture
def demo_on(monkeypatch):
    monkeypatch.setattr(get_settings(), "demo_mode", True)


def transcript(*student, tutee="Còn gì nữa không?"):
    out = []
    for i, s in enumerate(student):
        out.append({"role": "student", "text": s})
        if i < len(student) - 1:
            out.append({"role": "tutee", "text": tutee})
    return out


GOOD = [
    " ".join(k.content for k in RUBRIC.key_points),
    f"{RUBRIC.key_points[0].content}. {RUBRIC.key_points[1].content}",
    RUBRIC.key_points[1].content + " " + RUBRIC.key_points[2].content,
    RUBRIC.key_points[0].content + " " + RUBRIC.key_points[2].content,
]
POOR = ["Mình không nhớ rõ lắm.", "Không biết.", "Chịu thôi.", "Không rõ."]


def test_active_chi_khi_demo_bat_va_llm_unavailable(monkeypatch):
    err = AppError(503, "LLM_UNAVAILABLE", "x")
    monkeypatch.setattr(get_settings(), "demo_mode", False)
    assert demo.active(err) is False
    monkeypatch.setattr(get_settings(), "demo_mode", True)
    assert demo.active(err) is True
    assert demo.active(AppError(429, "TOKEN_BUDGET_EXCEEDED", "x")) is False
    assert demo.active(ValueError("x")) is False


def test_tutee_mo_dau_va_cau_hoi_khi_mat_ket_noi(demo_on):
    gw = DeadGateway()
    tutee = TuteeAgent(gw)
    assert tutee.opening_line(NODE).text == opening_template(NODE)
    ctx = SessionContext(
        node=NODE,
        transcript=transcript("Con trỏ lưu địa chỉ."),
        coverage=CoverageAnalysis(missing_points=[k.id for k in RUBRIC.key_points]),
    )
    q = tutee.next_question(ctx)
    assert q is not None and q.text and q.strategy is not None


def test_tat_demo_thi_loi_noi_len(monkeypatch):
    monkeypatch.setattr(get_settings(), "demo_mode", False)
    with pytest.raises(AppError) as e:
        TuteeAgent(DeadGateway()).opening_line(NODE)
    assert e.value.code == "LLM_UNAVAILABLE"
    with pytest.raises(AppError):
        JudgeAgent(DeadGateway(), runs=1).evaluate(transcript(*GOOD), RUBRIC, NODE.title, challenges_total=3)


def test_do_bao_phu_bang_tu_khoa(demo_on):
    cov = TuteeAgent(DeadGateway()).analyze_coverage(transcript(RUBRIC.key_points[0].content), NODE)
    assert cov.covered_points == [RUBRIC.key_points[0].id]
    assert RUBRIC.key_points[0].id not in cov.missing_points and cov.missing_points
    empty = TuteeAgent(DeadGateway()).analyze_coverage(transcript("Mình không biết."), NODE)
    assert empty.covered_points == []


def test_judge_du_phong_giang_dung_dat_giang_sai_khong_dat(demo_on):
    judge = JudgeAgent(DeadGateway(), runs=2)
    good = judge.evaluate(transcript(*GOOD), RUBRIC, NODE.title, challenges_total=3)
    poor = judge.evaluate(transcript(*POOR), RUBRIC, NODE.title, challenges_total=3)
    assert good.pass_check.verdict == Verdict.PASSED, good.pass_check
    assert poor.pass_check.verdict == Verdict.FAILED and poor.pass_check.missing_required_points
    assert len(good.criteria) == 5 and 0 <= good.pass_check.total_score <= 100


def test_cau_tra_loi_het_gio_khong_duoc_tinh_la_vuot_phan_bien(demo_on):
    text = "[SV] " + GOOD[0] + "\n[AI học trò] ?\n[SV] (hết giờ – chưa trả lời)\n[AI học trò] ?\n[SV] " + GOOD[1]
    r = demo.judge_result(text, RUBRIC, 2)
    assert r.passed_challenges == 1 and r.total_challenges == 2


def test_cay_mau_va_rubric_luu_san():
    tree = demo.seed_tree()
    assert len(tree.nodes) >= 8 and any(n.rubric for n in tree.nodes)
    r = demo.seed_rubric("n5_con_tro")
    assert r is not None and r.approved is False and r.key_points
    assert demo.seed_rubric("khong_co_nut_nay") is None
    assert demo.seed_tree() is not demo.seed_tree()  # bản sao, sửa không ảnh hưởng bản đệm


@pytest.mark.parametrize("operation", ["opening", "coverage", "question", "judge"])
@pytest.mark.parametrize("code", ["TOKEN_BUDGET_EXCEEDED", "LLM_CONFIG_ERROR"])
def test_demo_does_not_hide_budget_or_configuration_errors(demo_on, operation, code):
    class ErrorGateway(DeadGateway):
        def call_json(self, *args, **kwargs):
            raise AppError(429, code, "blocked")

    gateway = ErrorGateway()
    tutee = TuteeAgent(gateway)
    ctx = SessionContext(
        node=NODE,
        transcript=transcript("Con trỏ lưu địa chỉ."),
        coverage=CoverageAnalysis(missing_points=[point.id for point in RUBRIC.key_points]),
    )
    with pytest.raises(AppError) as error:
        if operation == "opening":
            tutee.opening_line(NODE)
        elif operation == "coverage":
            tutee.analyze_coverage(ctx.transcript, NODE)
        elif operation == "question":
            tutee.next_question(ctx)
        else:
            JudgeAgent(gateway, runs=1).evaluate(ctx.transcript, RUBRIC, NODE.title, challenges_total=3)
    assert error.value.code == code


@pytest.mark.parametrize(
    "scenario",
    [
        "Bạn nói đúng rồi. Bạn muốn thử tình huống khác không?",
        "Nghĩa là cách hoạt động sẽ thay đổi. Bạn muốn thử ví dụ khác không?",
    ],
)
def test_demo_fallback_still_rejects_answer_confirmation_and_teaching(demo_on, scenario):
    from app.ai.agents.guard import confirms_answer
    from app.ai.agents.tutee import role_violation
    from app.models.schemas.tree import ChallengeScenarioSchema

    node = NODE.model_copy(deep=True)
    node.rubric.scenarios = [ChallengeScenarioSchema(id="SC1", scenario=scenario, bloom_level="APPLY")]
    context = SessionContext(
        node=node,
        transcript=transcript("Mình đã giảng xong."),
        coverage=CoverageAnalysis(covered_points=[point.id for point in node.rubric.key_points]),
    )
    question = TuteeAgent(DeadGateway()).next_question(context)
    assert question is not None
    assert confirms_answer(question.text) is None
    assert role_violation(question.text, node.title) is None
