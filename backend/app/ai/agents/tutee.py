"""Tutee Agent – "học trò tò mò" (mục 6.2, Phụ lục A.1). Chủ: Đăng (C1-03, C1-04, C1-17).

Ràng buộc BR-04: không giảng hộ, không đưa đáp án, không khen khi lập luận chưa chặt.
Thứ tự chiến lược (Hình 6.6): MISSING_KEY_POINT → MISCONCEPTION_PROBE → EDGE_CASE → TRANSFER.
"""

from app.ai.gateway import LLMGateway
from app.models.schemas.session import Question
from app.models.schemas.tree import Node


class TuteeAgent:
    def __init__(self, gateway: LLMGateway, max_questions: int = 4):
        self.gateway = gateway
        self.max_questions = max_questions

    def opening_line(self, node: Node) -> Question:
        """C1-03 – câu mở đầu đúng vai, nhờ SV giảng khái niệm."""
        raise NotImplementedError("C1-03")

    def analyze_coverage(self, transcript: str, node: Node) -> dict:
        """C1-04 – ý đã nêu / còn thiếu / quan niệm sai phát hiện."""
        raise NotImplementedError("C1-04")

    def next_question(self, ctx: dict) -> Question | None:
        """C1-04 – chọn chiến lược theo Hình 6.6, sinh câu hỏi (prompts/tutee.md). None ⇒ dừng vòng."""
        raise NotImplementedError("C1-04")
