"""Judge Agent – chấm độc lập 5 tiêu chí (mục 6.3, Phụ lục A.2). Chủ: Đăng (C1-05, C1-16).

Chấm ≥ 2 lần (đảo thứ tự tiêu chí và ý chính), nhiệt độ 0; lệch kết luận ⇒ chấm lần 3, lấy đa số.
"""

from app.ai.gateway import LLMGateway
from app.models.enums import CriterionCode, Verdict
from app.models.schemas.session import DEFAULT_CRITERION_WEIGHTS, JudgeResult
from app.models.schemas.tree import Rubric

# Bảng 6.4 – trọng số mặc định (định nghĩa trong hợp đồng phiên, C1-01)
DEFAULT_WEIGHTS: dict[CriterionCode, float] = DEFAULT_CRITERION_WEIGHTS


class JudgeAgent:
    def __init__(self, gateway: LLMGateway, runs: int = 2):
        self.gateway = gateway
        self.runs = runs

    def evaluate(self, transcript: str, rubric: Rubric) -> JudgeResult:
        """C1-05 – chỉ nhận transcript + rubric, không thấy lịch sử nhập vai (mục 6.3.3)."""
        raise NotImplementedError("C1-05")


def apply_pass_rule(result: JudgeResult, rubric: Rubric) -> tuple[float, Verdict]:
    """BR-03: Đạt ⇔ S ≥ θ ∧ đủ mọi ý chính bắt buộc ∧ vượt ≥ k câu phản biện
    ∧ không còn quan niệm sai nghiêm trọng chưa được sửa. S = Σ wᵢ·sᵢ (mục 6.3.2).
    TC10: điểm 82 nhưng thiếu KP3 ⇒ FAILED."""
    raise NotImplementedError("C1-05")
