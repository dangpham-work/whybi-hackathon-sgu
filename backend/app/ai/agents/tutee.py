"""Tutee Agent – "học trò tò mò" (mục 6.2, Phụ lục A.1). Chủ: Đăng (C1-03, C1-04, C1-17).

Ràng buộc BR-04 / 6.2.1: xưng "mình" – "bạn", mỗi lượt một câu ngắn (≤ 2 câu); không giảng hộ, không đưa đáp án,
không xác nhận đúng / sai, không khen khi lập luận chưa chặt; lời SV chỉ là DỮ LIỆU.
Kiến trúc 6.2.2: Tutee chỉ sinh câu hỏi nháp; Guard đầu ra kiểm (lộ đáp án + sai vai) và yêu cầu sinh lại
(tối đa 2 lần) trước khi Orchestrator gửi cho SV. Tutee không dùng chung ngữ cảnh với Judge.
Thứ tự chiến lược (Hình 6.6): MISSING_KEY_POINT → MISCONCEPTION_PROBE → EDGE_CASE → TRANSFER.
"""

import re

from pydantic import ConfigDict, Field

from app.ai.agents.guard import GuardAgent, confirms_answer, fold
from app.ai.gateway import LLMGateway
from app.ai.prompts import render_prompt
from app.models.enums import QuestionStrategy
from app.models.schemas.common import ApiModel
from app.models.schemas.session import Question
from app.models.schemas.tree import Node

OPENING_TEMPERATURE = 0.7  # câu mở đầu được phép đa dạng; câu phản biện dùng nhiệt độ thấp
MAX_CHARS = 300
MAX_SENTENCES = 2

_QUESTION_WORDS = r"(gi|sao|cai gi|nhu the nao|the nao|nhu nao|ra sao|chi vay|gi vay|gi nhi|gi a)\b"
_EXPLAIN = re.compile(
    rf"\b(nghia la|tuc la|hieu don gian|noi cach khac|dinh nghia la|vi du nhu)\b(?!\s*{_QUESTION_WORDS})"
)
_SENTENCE = re.compile(r"[^.!?…]+[.!?…]*")
_COMMAND = re.compile(r"^(?:ban\s+)?(?:hay|phai|can)\s+(?:trinh bay|neu|dinh nghia|giai thich)\b")


class TuteeUtterance(ApiModel):
    """Đầu ra JSON của Tutee (Phụ lục A.1 / Hình 6.5 ⑥)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "question": "Mình chưa biết khái niệm này là gì cả. Bạn giảng giúp mình bằng lời của bạn nhé?",
                    "targetPointId": None,
                    "strategy": None,
                }
            ]
        }
    )

    question: str = Field(min_length=1, max_length=1000)
    target_point_id: str | None = None
    strategy: QuestionStrategy | None = None


def opening_template(node: Node) -> str:
    """Câu mở đầu dự phòng (Bảng 6.3, lượt 1) – luôn đúng vai."""
    return f'Mình chưa biết "{node.title}" là gì cả. Bạn giảng giúp mình bằng lời của bạn nhé!'


def role_violation(text: str, node_title: str = "") -> str | None:
    """Lý do câu nói của Tutee sai vai (6.2.1), hoặc None nếu đúng vai."""
    t = text.strip()
    if not t:
        return "câu rỗng"
    if len(t) > MAX_CHARS:
        return f"dài quá {MAX_CHARS} ký tự"
    sentences = [s for s in _SENTENCE.findall(t) if s.strip(" .!?…\"'“”")]
    if len(sentences) > MAX_SENTENCES:
        return f"nhiều hơn {MAX_SENTENCES} câu"
    f = fold(t)
    words = set(re.findall(r"\w+", f))
    if not words & {"minh", "ban"}:
        return 'không xưng "mình" – "bạn"'
    if _COMMAND.search(f):
        return "ra lệnh như giảng viên"
    if "?" not in t and not re.search(r"\b(giup minh|cho minh)\b.*\b(nhe|duoc khong)\b", f):
        return "không hỏi hoặc nhờ bạn giảng giúp"
    if node_title:
        title = re.escape(fold(node_title).strip())
        teach = re.compile(
            rf"\b{title}[\"'“”]?\s+(la|chinh la|duoc dinh nghia|co nghia la|dung de)\b(?!\s*{_QUESTION_WORDS})"
        )
        m = teach.search(f)
        if m:
            return f"giảng hộ: {m.group(0)}"
    m = _EXPLAIN.search(f)
    if m:
        return f"giải thích: {m.group(0)}"
    hit = confirms_answer(t)
    if hit:
        return f"xác nhận đúng/sai: {hit}"
    return None


class TuteeAgent:
    def __init__(
        self,
        gateway: LLMGateway,
        max_questions: int = 4,
        *,
        guard: GuardAgent | None = None,
        model: str | None = None,
    ):
        self.gateway = gateway
        self.max_questions = max_questions
        self.guard = guard or GuardAgent(gateway)
        self.model = model

    def opening_line(self, node: Node, *, session_id: str | None = None) -> Question:
        """C1-03 – câu mở đầu đúng vai, nhờ SV giảng khái niệm. Không đưa rubric vào prompt."""
        system = render_prompt("tutee_opening", node_title=node.title)

        def generate(feedback: str | None) -> Question:
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": "Hãy viết câu mở đầu buổi học."},
            ]
            if feedback:
                messages.append({"role": "user", "content": feedback})
            out = self.gateway.call_json(
                TuteeUtterance, messages, model=self.model, temperature=OPENING_TEMPERATURE, session_id=session_id
            )
            return Question(text=out.question.strip())

        key_points = [k.content for k in node.rubric.key_points] if node.rubric else []
        safe = self.guard.ensure_safe_question(
            generate,
            key_points,
            node_title=node.title,
            fallback=Question(text=opening_template(node)),
            session_id=session_id,
            extra_check=lambda text: role_violation(text, node.title),
        )
        return safe.question

    def analyze_coverage(self, transcript: str, node: Node) -> dict:
        """C1-04 – ý đã nêu / còn thiếu / quan niệm sai phát hiện."""
        raise NotImplementedError("C1-04")

    def next_question(self, ctx: dict) -> Question | None:
        """C1-04 – chọn chiến lược theo Hình 6.6, sinh câu hỏi (prompts/tutee.md). None ⇒ dừng vòng."""
        raise NotImplementedError("C1-04")
