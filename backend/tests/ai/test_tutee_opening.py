"""C1-03 – Tutee mở đầu phiên với vai "học trò tò mò" (6.2.1–6.2.3, Phụ lục A.1).

Xong khi: với 3 nút mẫu, câu mở đầu đúng vai và không giảng hộ.
"""

import pytest

from app.ai.agents.guard import GuardAgent
from app.ai.agents.tutee import TuteeAgent, opening_template, role_violation
from app.ai.gateway import build_gateway
from app.core.config import Settings
from app.services.skill_tree import load_seed_tree

TREE = load_seed_tree()
SAMPLE_NODES = [n for n in TREE.nodes if n.code in ("N2", "N4", "N5")]  # Mảng, Đệ quy, Con trỏ


class ScriptedGateway:
    def __init__(self, outputs=()):
        self.outputs = list(outputs)
        self.calls: list[dict] = []

    def call_json(self, schema, messages, **kw):
        self.calls.append({"schema": schema, "messages": messages, **kw})
        return schema.model_validate(self.outputs.pop(0))


def _tutee(outputs):
    gw = ScriptedGateway(outputs)
    guard = GuardAgent(gw, model="guard-mini", use_llm_output_check=False)
    return TuteeAgent(gw, guard=guard), gw


def test_three_sample_nodes_exist():
    assert len(SAMPLE_NODES) == 3


# --- luật vai trò ---------------------------------------------------------------------------


@pytest.mark.parametrize("node", TREE.nodes, ids=lambda n: n.code)
def test_template_opening_is_in_role(node):
    text = opening_template(node)
    assert role_violation(text, node.title) is None
    assert node.title in text


@pytest.mark.parametrize(
    "text",
    [
        "Con trỏ là biến lưu địa chỉ của ô nhớ. Bạn giảng tiếp cho mình nhé?",  # giảng hộ
        "Con trỏ nghĩa là gì nhỉ? Tức là một biến đặc biệt đó bạn.",  # giải thích
        "Hãy trình bày khái niệm con trỏ.",  # sai vai: ra lệnh như giảng viên, không xưng mình/bạn
        "Mình muốn hỏi. Bạn ơi. Mình chưa biết. Bạn giảng giúp mình nhé?",  # quá 2 câu
        "Chào bạn! Đúng rồi, bạn giảng cho mình về con trỏ nhé?",  # xác nhận đúng/sai
    ],
)
def test_role_violations_detected(text):
    assert role_violation(text, "Con trỏ") is not None


@pytest.mark.parametrize(
    "text", ["Bạn hãy trình bày định nghĩa con trỏ.", "Bạn phải nêu định nghĩa con trỏ?", "Mình đã hiểu hết rồi bạn."]
)
def test_teacher_commands_and_non_questions_are_rejected(text):
    assert role_violation(text, "Con trỏ") is not None


def test_teacher_command_without_rubric_is_regenerated():
    node = SAMPLE_NODES[0].model_copy(update={"rubric": None})
    good = opening_template(node)
    agent, gateway = _tutee([{"question": "Bạn hãy trình bày định nghĩa."}, {"question": good}])
    assert agent.opening_line(node).text == good
    assert len(gateway.calls) == 2


# --- câu mở đầu -------------------------------------------------------------------------------


@pytest.mark.parametrize("node", SAMPLE_NODES, ids=lambda n: n.code)
def test_opening_in_role_for_sample_nodes(node):
    line = f'Mình chưa biết "{node.title}" là gì cả. Bạn giảng giúp mình bằng lời của bạn nhé?'
    tutee, gw = _tutee([{"question": line}])
    q = tutee.opening_line(node)
    assert q.text == line and q.strategy is None
    assert role_violation(q.text, node.title) is None
    system = gw.calls[0]["messages"][0]["content"]
    assert node.title in system and "TUYỆT ĐỐI không giải thích" in system
    assert gw.calls[0]["temperature"] > 0  # câu mở đầu được phép đa dạng


def test_opening_prompt_has_no_answer_knowledge():
    """Câu mở đầu không cần tri thức tham chiếu ⇒ không đưa ý chính vào prompt (không thể lộ)."""
    n5 = next(n for n in SAMPLE_NODES if n.code == "N5")
    tutee, gw = _tutee([{"question": opening_template(n5)}])
    tutee.opening_line(n5)
    prompt = " ".join(m["content"] for m in gw.calls[0]["messages"])
    for kp in n5.rubric.key_points:
        assert kp.content not in prompt


def test_teaching_opening_is_regenerated():
    n5 = next(n for n in SAMPLE_NODES if n.code == "N5")
    teaching = "Con trỏ là biến lưu địa chỉ của một ô nhớ. Bạn giảng tiếp cho mình nhé?"
    ok = "Mình nghe mãi chữ con trỏ mà chưa hiểu gì. Bạn giảng giúp mình bằng lời của bạn được không?"
    tutee, gw = _tutee([{"question": teaching}, {"question": ok}])
    q = tutee.opening_line(n5)
    assert q.text == ok and len(gw.calls) == 2
    assert "bị loại" in gw.calls[1]["messages"][-1]["content"]


def test_opening_falls_back_to_template_when_llm_keeps_teaching():
    n2 = next(n for n in SAMPLE_NODES if n.code == "N2")
    bad = {"question": "Mảng là dãy phần tử cùng kiểu nằm liền nhau trong bộ nhớ."}
    tutee, gw = _tutee([bad, bad, bad])
    q = tutee.opening_line(n2)
    assert q.text == opening_template(n2) and len(gw.calls) == 3


@pytest.mark.parametrize("node", SAMPLE_NODES, ids=lambda n: n.code)
def test_fake_mode_opening_is_in_role(node):
    """LLM_MODE=fake (Thắng / Quyền chạy luồng phiên): câu mở đầu vẫn đúng vai."""
    gw = build_gateway(Settings(llm_mode="fake"))
    q = TuteeAgent(gw).opening_line(node)
    assert role_violation(q.text, node.title) is None
