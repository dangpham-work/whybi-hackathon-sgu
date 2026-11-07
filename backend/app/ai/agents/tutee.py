"""Tutee Agent – "học trò tò mò" (mục 6.2, Phụ lục A.1). Chủ: Đăng (C1-03, C1-04, C1-17).

Ràng buộc BR-04 / 6.2.1: xưng "mình" – "bạn", mỗi lượt một câu ngắn (≤ 2 câu); không giảng hộ, không đưa đáp án,
không xác nhận đúng / sai, không khen khi lập luận chưa chặt; lời SV chỉ là DỮ LIỆU.
Kiến trúc 6.2.2: Tutee chỉ sinh câu hỏi nháp; Guard đầu ra kiểm (lộ đáp án + sai vai) và yêu cầu sinh lại
(tối đa 2 lần) trước khi Orchestrator gửi cho SV. Tutee không dùng chung ngữ cảnh với Judge.
Thứ tự chiến lược (Hình 6.6): MISSING_KEY_POINT → MISCONCEPTION_PROBE → EDGE_CASE → TRANSFER.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import ConfigDict, Field

from app.ai import demo
from app.ai.agents.guard import GuardAgent, confirms_answer, fold, leaked_point
from app.ai.gateway import LLMGateway
from app.ai.prompts import format_transcript, render_prompt, wrap_student_text
from app.core.errors import AppError
from app.models.enums import QuestionStrategy
from app.models.schemas.common import ApiModel
from app.models.schemas.session import Question
from app.models.schemas.tree import Node, Rubric

OPENING_TEMPERATURE = 0.7  # câu mở đầu được phép đa dạng; câu phản biện dùng nhiệt độ thấp
QUESTION_TEMPERATURE = 0.3
MIN_QUESTIONS, MAX_QUESTIONS = 3, 5  # FR-TB-08: 3–5 câu phản biện
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
        fallback = Question(text=opening_template(node))
        try:
            safe = self.guard.ensure_safe_question(
                generate,
                key_points,
                node_title=node.title,
                fallback=fallback,
                session_id=session_id,
                extra_check=lambda text: role_violation(text, node.title),
            )
        except AppError as exc:
            if not demo.active(exc):
                raise
            return fallback  # C1-13: LLM mất kết nối ⇒ câu mở đầu mẫu
        return safe.question

    def analyze_coverage(
        self, transcript: str | list[dict[str, Any]], node: Node, *, session_id: str | None = None
    ) -> CoverageAnalysis:
        """C1-04 – coverage map: ý đã nêu / còn thiếu / quan niệm sai phát hiện, chuẩn hóa theo id rubric."""
        rubric = _rubric(node)
        system = render_prompt(
            "tutee_coverage",
            node_title=node.title,
            key_points=_list_points(rubric),
            misconceptions=_list_misconceptions(rubric),
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": wrap_student_text(format_transcript(transcript))},
        ]
        try:
            raw = self.gateway.call_json(
                CoverageAnalysis, messages, model=self.model, temperature=0, session_id=session_id
            )
        except AppError as exc:
            if not demo.active(exc):
                raise
            # C1-13: LLM mất kết nối ⇒ đối chiếu từ khóa của lời SV với từng ý chính
            raw = CoverageAnalysis(covered_points=demo.covered_points(format_transcript(transcript), rubric))
        return raw.normalised(rubric)

    def next_question(self, ctx: SessionContext) -> Question | None:
        """C1-04 – chọn chiến lược theo Hình 6.6, sinh câu hỏi (prompts/tutee.md), qua Guard đầu ra.
        None ⇒ dừng vòng phản biện. Chiến lược / mục tiêu do code chọn, LLM chỉ diễn đạt."""
        choice = choose_strategy(ctx)
        if choice is None:
            return None
        strategy, target = choice
        node, rubric = ctx.node, _rubric(ctx.node)
        system = render_prompt(
            "tutee",
            node_title=node.title,
            key_points=_list_points(rubric),
            misconceptions=_list_misconceptions(rubric),
            scenarios="; ".join(f"{s.id}: {s.scenario}" for s in rubric.scenarios) or "-",
            retrieved_chunks=ctx.retrieved_chunks or "-",
            covered=", ".join(ctx.coverage.covered_points) or "-",
            missing=", ".join(ctx.coverage.missing_points) or "-",
            detected=", ".join(ctx.coverage.detected_misconceptions) or "-",
            asked_questions=" | ".join(q.text for q in ctx.asked) or "-",
            remaining=str(ctx.max_questions - len(ctx.asked)),
            strategy=strategy.value,
            target_id=target or "-",
            strategy_hint=STRATEGY_HINTS[strategy],
        )
        transcript = wrap_student_text(format_transcript(ctx.transcript))

        def generate(feedback: str | None) -> Question:
            messages = [{"role": "system", "content": system}]
            if feedback:
                messages.append({"role": "user", "content": feedback})
            messages.append({"role": "user", "content": transcript})
            out = self.gateway.call_json(
                TuteeUtterance, messages, model=self.model, temperature=QUESTION_TEMPERATURE, session_id=ctx.session_id
            )
            return Question(text=out.question.strip(), strategy=strategy, target_point_id=target)

        fallback = fallback_question(node, strategy, target)
        try:
            safe = self.guard.ensure_safe_question(
                generate,
                [k.content for k in rubric.key_points],
                node_title=node.title,
                fallback=fallback,
                session_id=ctx.session_id,
                extra_check=lambda text: role_violation(text, node.title),
            )
        except AppError as exc:
            if not demo.active(exc):
                raise
            return fallback  # C1-13: LLM mất kết nối ⇒ câu từ ngân hàng tình huống của rubric
        return safe.question


# --- C1-04: coverage map, chọn chiến lược (Hình 6.6), ngân hàng câu hỏi dự phòng ----------------

STRATEGY_HINTS: dict[QuestionStrategy, str] = {
    QuestionStrategy.MISSING_KEY_POINT: (
        'Hỏi một câu "ngây thơ" để bạn ấy TỰ nói ra ý mục tiêu; không nhắc nội dung ý đó.'
    ),
    QuestionStrategy.MISCONCEPTION_PROBE: (
        "Đưa một tình huống khiến quan niệm sai mục tiêu tự lộ ra mâu thuẫn; không sửa trực tiếp."
    ),
    QuestionStrategy.EDGE_CASE: 'Hỏi tình huống biên mục tiêu dạng "Nếu … thì sao?".',
    QuestionStrategy.TRANSFER: "Hỏi cách áp dụng khái niệm vào một ngữ cảnh / bài toán mới (mức Bloom cao hơn).",
}  # fmt: skip


class CoverageAnalysis(ApiModel):
    """Coverage map của Tutee sau mỗi lượt SV (Hình 6.4 – Bộ nhớ phiên)."""

    covered_points: list[str] = []
    missing_points: list[str] = []
    detected_misconceptions: list[str] = []
    corrected_misconceptions: list[str] = []

    def normalised(self, rubric: Rubric) -> CoverageAnalysis:
        """Bỏ id lạ; vừa "đã nêu" vừa "thiếu" ⇒ thiếu; missing = ý bắt buộc chưa nêu."""
        claimed_missing = set(self.missing_points)
        covered = [k.id for k in rubric.key_points if k.id in set(self.covered_points) and k.id not in claimed_missing]
        missing = [k.id for k in rubric.key_points if k.is_required and k.id not in covered]
        mc_ids = [m.id for m in rubric.misconceptions]
        return CoverageAnalysis(
            covered_points=covered,
            missing_points=missing,
            detected_misconceptions=[m for m in mc_ids if m in set(self.detected_misconceptions)],
            corrected_misconceptions=[m for m in mc_ids if m in set(self.corrected_misconceptions)],
        )


@dataclass
class SessionContext:
    """Trạng thái phiên đưa cho Tutee mỗi lượt (Hình 6.5 ③). Orchestrator (C1-07) giữ và cập nhật."""

    node: Node
    transcript: str | list[dict[str, Any]]
    coverage: CoverageAnalysis
    asked: list[Question] = field(default_factory=list)
    max_questions: int = 4
    retrieved_chunks: str = ""  # RAG (C1-11)
    session_id: str | None = None

    def __post_init__(self) -> None:
        self.max_questions = max(MIN_QUESTIONS, min(MAX_QUESTIONS, self.max_questions))


def _rubric(node: Node) -> Rubric:
    return node.rubric or Rubric(key_points=[])


def _list_points(rubric: Rubric) -> str:
    return (
        "\n".join(f"- {k.id} ({'bắt buộc' if k.is_required else 'phụ'}): {k.content}" for k in rubric.key_points) or "-"
    )


def _list_misconceptions(rubric: Rubric) -> str:
    return "\n".join(f"- {m.id}: {m.content}" for m in rubric.misconceptions) or "-"


def choose_strategy(ctx: SessionContext) -> tuple[QuestionStrategy, str | None] | None:
    """Hình 6.6: đủ N câu ⇒ dừng; còn ý bắt buộc chưa nêu ⇒ MISSING_KEY_POINT; có quan niệm sai chưa sửa ⇒
    MISCONCEPTION_PROBE; còn tình huống biên chưa thử ⇒ EDGE_CASE; đã vững ⇒ TRANSFER; hết ⇒ dừng sớm
    (nhưng luôn hỏi đủ tối thiểu 3 câu – FR-TB-08). Không hỏi lại cùng (chiến lược, mục tiêu)."""
    if len(ctx.asked) >= ctx.max_questions:
        return None
    rubric, cov = _rubric(ctx.node), ctx.coverage
    used = {(q.strategy, q.target_point_id) for q in ctx.asked}
    targeted = {q.target_point_id for q in ctx.asked if q.target_point_id}

    required = [k.id for k in rubric.key_points if k.is_required]
    for kp in required:
        if kp in cov.missing_points and kp not in targeted:
            return QuestionStrategy.MISSING_KEY_POINT, kp
    corrected = set(cov.corrected_misconceptions)
    for mc in cov.detected_misconceptions:
        if mc not in corrected and mc not in targeted:
            return QuestionStrategy.MISCONCEPTION_PROBE, mc
    for sc in rubric.scenarios:
        if sc.id not in targeted:
            return QuestionStrategy.EDGE_CASE, sc.id
    solid = not cov.missing_points and not (set(cov.detected_misconceptions) - corrected)
    if solid and (QuestionStrategy.TRANSFER, None) not in used:
        return QuestionStrategy.TRANSFER, None
    if len(ctx.asked) >= MIN_QUESTIONS:
        return None
    # Rubric mỏng mà chưa đủ 3 câu: cho phép hỏi lại ý còn thiếu, hoặc câu tình huống / chuyển giao chung.
    for kp in cov.missing_points:
        return QuestionStrategy.MISSING_KEY_POINT, kp
    if (QuestionStrategy.TRANSFER, None) not in used:
        return QuestionStrategy.TRANSFER, None
    return QuestionStrategy.EDGE_CASE, None


def fallback_question(node: Node, strategy: QuestionStrategy, target: str | None) -> Question:
    """Câu hỏi mẫu từ ngân hàng tình huống khi Guard loại cả 3 lần sinh (Hình 6.6). Không chứa nội dung ý chính."""
    rubric, title = _rubric(node), node.title
    text = None
    if strategy == QuestionStrategy.MISCONCEPTION_PROBE:
        text = next((m.probe_question for m in rubric.misconceptions if m.id == target and m.probe_question), None)
    elif strategy == QuestionStrategy.EDGE_CASE:
        sc = next((s.scenario for s in rubric.scenarios if s.id == target), None)
        if sc:
            text = f"Mình thắc mắc thế này: {sc[0].lower()}{sc[1:]}"
    elif strategy == QuestionStrategy.TRANSFER:
        text = f'Thế "{title}" giúp được gì khi mình gặp một bài toán thực tế? Bạn cho mình một ví dụ được không?'
    if text and (
        role_violation(text, title) is not None
        or leaked_point(text, [k.content for k in rubric.key_points], ignore=title) is not None
    ):
        text = None  # câu trong ngân hàng (do người soạn rubric viết) lỡ chứa ý chính ⇒ dùng câu chung
    if not text:
        text = f'Mình vẫn chưa hình dung hết về "{title}". Còn điều gì quan trọng mà bạn chưa kể cho mình không?'
    return Question(text=text, strategy=strategy, target_point_id=target)
