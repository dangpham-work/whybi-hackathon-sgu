"""Judge Agent – chấm độc lập 5 tiêu chí (mục 6.3, Phụ lục A.2). Chủ: Đăng (C1-05, C1-16).

- Chỉ nhận transcript + rubric, không nhận lịch sử nhập vai của Tutee (6.3.3).
- Nhiệt độ 0; chấm `runs` lần (mặc định 2), lần lẻ đảo thứ tự tiêu chí và ý chính; lệch kết luận ⇒ chấm thêm
  một lần, lấy đa số. Điểm từng tiêu chí = trung bình các lần thuộc nhóm đa số.
- Kết luận theo BR-03 (`JudgeResult.check_pass`, hợp đồng C1-01).
- Phản hồi (6.3.4): điểm mạnh trước, gợi ý ôn dạng câu hỏi gợi mở và KHÔNG lộ ý chính, kèm trang giáo trình.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from app.ai import demo
from app.ai.gateway import LLMGateway
from app.ai.prompts import render_prompt, wrap_student_text
from app.core.errors import AppError
from app.models.enums import CriterionCode, Verdict
from app.models.schemas.session import (
    DEFAULT_CRITERION_WEIGHTS,
    CriterionResult,
    CriterionScore,
    JudgeResult,
    PassCheck,
)
from app.models.schemas.tree import Rubric

# Bảng 6.4 – trọng số mặc định (định nghĩa trong hợp đồng phiên, C1-01)
DEFAULT_WEIGHTS: dict[CriterionCode, float] = DEFAULT_CRITERION_WEIGHTS

# Bảng 6.4 – câu hỏi đánh giá và mô tả mức neo (Cao / Trung bình / Thấp) để giảm chấm cảm tính
ANCHORS: dict[CriterionCode, tuple[str, str, str, str]] = {
    CriterionCode.CORRECTNESS: (
        "Có phát biểu sai về kiến thức không?",
        "Không sai",
        "Sai nhỏ, không ảnh hưởng bản chất",
        "Sai bản chất",
    ),
    CriterionCode.COVERAGE: ("Nêu được bao nhiêu ý chính bắt buộc?", "Đủ mọi ý", "Thiếu 1 ý", "Thiếu từ 2 ý"),
    CriterionCode.ESSENCE: (
        "Có giải thích được lý do, cơ chế không?",
        "Giải thích cơ chế rõ",
        "Nêu được nhưng mơ hồ",
        "Chỉ định nghĩa thuộc lòng",
    ),
    CriterionCode.ROBUSTNESS: (
        "Trả lời được bao nhiêu câu phản biện?",
        "Từ 80% câu",
        "50–80% câu",
        "Dưới 50% câu",
    ),
    CriterionCode.CLARITY: (
        "Có trình bày có cấu trúc, có ví dụ?",
        "Mạch lạc, có ví dụ",
        "Hiểu được",
        "Rời rạc",
    ),
}

ROLE_LABEL = {"student": "SV", "tutee": "AI học trò"}
_WORD = re.compile(r"\w+", re.U)
LEAK_OVERLAP = 0.6  # gợi ý chứa ≥ 60% từ của một ý chính ⇒ coi là lộ đáp án


@dataclass
class JudgeOutcome:
    """Kết quả chấm đã áp BR-03 – SessionOrchestrator (C1-07) dựng SessionResult từ đây."""

    result: JudgeResult
    pass_check: PassCheck
    criteria: list[CriterionResult]
    strengths: list[str] = field(default_factory=list)
    review_hints: list[str] = field(default_factory=list)
    source_pages: list[int] = field(default_factory=list)

    @property
    def verdict(self) -> Verdict:
        return self.pass_check.verdict

    @property
    def total_score(self) -> float:
        return self.pass_check.total_score


def format_transcript(transcript: str | list[dict[str, Any]]) -> str:
    """Lượt hội thoại → văn bản có nhãn người nói. Chấp nhận chuỗi sẵn có."""
    if isinstance(transcript, str):
        return transcript
    lines = []
    for t in transcript:
        who = ROLE_LABEL.get(str(t.get("role", "student")).lower(), "SV")
        lines.append(f"[{who}] {t.get('text', '')}")
    return "\n".join(lines)


def _words(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text)}


def leaks_key_point(text: str, rubric: Rubric, threshold: float = LEAK_OVERLAP) -> bool:
    """Heuristic rẻ: câu chứa phần lớn từ của một ý chính ⇒ nói ra đáp án. Guard (C1-06) kiểm kỹ hơn."""
    words = _words(text)
    for kp in rubric.key_points:
        kw = _words(kp.content)
        if kw and len(words & kw) / len(kw) >= threshold:
            return True
    return False


class JudgeAgent:
    def __init__(self, gateway: LLMGateway, runs: int = 2, model: str | None = None):
        self.gateway = gateway
        self.runs = max(1, runs)
        self.model = model

    # --- prompt ---

    def _system_prompt(self, node_title: str, rubric: Rubric, reverse: bool) -> str:
        codes = list(CriterionCode)
        kps = list(rubric.key_points)
        if reverse:
            codes.reverse()
            kps.reverse()
        criteria = "\n".join(
            f"- {c.value} (trọng số {int(DEFAULT_WEIGHTS[c] * 100)}%): {q} Cao: {hi} / Trung bình: {mid} / Thấp: {lo}"
            for c in codes
            for q, hi, mid, lo in [ANCHORS[c]]
        )
        key_points = "\n".join(f"- {k.id} ({'bắt buộc' if k.is_required else 'phụ'}): {k.content}" for k in kps) or "-"
        mcs = (
            "\n".join(
                f"- {m.id} ({'nghiêm trọng' if m.is_critical else 'nhẹ'}): {m.content}" for m in rubric.misconceptions
            )
            or "-"
        )
        scenarios = "\n".join(f"- {s.id}: {s.scenario}" for s in rubric.scenarios) or "-"
        return render_prompt(
            "judge",
            node_title=node_title,
            criteria_with_anchors=criteria,
            key_points=key_points,
            misconceptions=mcs,
            scenarios=scenarios,
        )

    def _messages(self, transcript_text: str, node_title: str, rubric: Rubric, reverse: bool) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": self._system_prompt(node_title, rubric, reverse)},
            {
                "role": "user",
                "content": "TRANSCRIPT (lời giảng + các cặp hỏi–đáp):\n" + wrap_student_text(transcript_text),
            },
        ]

    # --- chuẩn hóa đầu ra LLM theo rubric ---

    @staticmethod
    def _normalise(r: JudgeResult, rubric: Rubric, challenges_total: int | None) -> JudgeResult:
        kp_ids = [k.id for k in rubric.key_points]
        mc_ids = {m.id for m in rubric.misconceptions}
        missing_claimed = set(r.missing_points)
        covered = [k for k in kp_ids if k in set(r.covered_points) and k not in missing_claimed]
        missing = [k for k in kp_ids if k not in covered]
        mcs = [m for m in r.misconceptions if m.id in mc_ids]
        passed = r.passed_challenges
        total = challenges_total if challenges_total is not None else r.total_challenges
        if total is not None:
            passed = min(passed, total)
        return r.model_copy(
            update={
                "covered_points": covered,
                "missing_points": missing,
                "misconceptions": mcs,
                "passed_challenges": passed,
                "total_challenges": total,
            }
        )

    # --- chấm ---

    def _judge_once(self, text, node_title, rubric, reverse, challenges_total, session_id) -> JudgeResult:
        try:
            raw = self.gateway.call_json(
                JudgeResult,
                self._messages(text, node_title, rubric, reverse),
                model=self.model,
                temperature=0,
                session_id=session_id,
                use_cache=False,
            )
        except AppError as exc:
            if not demo.active(exc):
                raise
            raw = demo.judge_result(text, rubric, challenges_total)  # C1-13: chấm dự phòng bằng từ khóa
        return self._normalise(raw, rubric, challenges_total)

    def evaluate(
        self,
        transcript: str | list[dict[str, Any]],
        rubric: Rubric,
        node_title: str = "",
        *,
        challenges_total: int | None = None,
        pass_threshold: int | None = None,
        min_passed_challenges: int | None = None,
        weights: dict[CriterionCode, float] | None = None,
        session_id: str | None = None,
    ) -> JudgeOutcome:
        """C1-05 – chỉ nhận transcript + rubric, không thấy lịch sử nhập vai (mục 6.3.3)."""
        text = format_transcript(transcript)

        def check(r: JudgeResult) -> PassCheck:
            return r.check_pass(
                rubric, pass_threshold=pass_threshold, min_passed_challenges=min_passed_challenges, weights=weights
            )

        runs: list[JudgeResult] = []
        for i in range(self.runs):
            runs.append(self._judge_once(text, node_title, rubric, i % 2 == 1, challenges_total, session_id))
        verdicts = [check(r).verdict for r in runs]
        if len(set(verdicts)) > 1 and len(runs) % 2 == 0:  # lệch kết luận ⇒ chấm thêm, lấy đa số
            runs.append(self._judge_once(text, node_title, rubric, len(runs) % 2 == 1, challenges_total, session_id))
            verdicts.append(check(runs[-1]).verdict)

        majority = Counter(verdicts).most_common(1)[0][0]
        group = [r for r, v in zip(runs, verdicts, strict=True) if v == majority]
        merged = self._merge(group, len(runs))
        pc = check(merged)
        if pc.verdict != majority:  # trung bình đẩy qua ngưỡng ⇒ giữ nguyên lần chấm đại diện
            merged = group[0].model_copy(update={"judge_runs": len(runs)})
            pc = check(merged)
        return JudgeOutcome(
            result=merged,
            pass_check=pc,
            criteria=merged.weighted_criteria(weights),
            strengths=merged.strengths[:3],
            review_hints=self._review_hints(merged, rubric),
            source_pages=list(rubric.source_pages),
        )

    @staticmethod
    def _merge(group: list[JudgeResult], total_runs: int) -> JudgeResult:
        base = group[0]
        criteria = [
            CriterionScore(
                code=c.code,
                score=round(sum(r.score_of(c.code) for r in group) / len(group), 2),
                rationale=c.rationale,
                evidence=c.evidence,
            )
            for c in base.criteria
        ]
        return base.model_copy(update={"criteria": criteria, "judge_runs": total_runs})

    # --- phản hồi (6.3.4) ---

    @staticmethod
    def _review_hints(r: JudgeResult, rubric: Rubric) -> list[str]:
        hints = [h.strip() for h in r.review_hints if h.strip() and not leaks_key_point(h, rubric)]
        if not hints:
            probes = {m.id: m.probe_question for m in rubric.misconceptions if m.probe_question}
            hints = [
                probes[m.id]
                for m in r.misconceptions
                if not m.corrected and m.id in probes and not leaks_key_point(probes[m.id], rubric)
            ]
        if not hints and r.missing_points:
            pages = ", ".join(str(p) for p in rubric.source_pages)
            where = f" – thử đọc lại trang {pages}" if pages else ""
            hints = [f"Theo bạn, còn khía cạnh nào của khái niệm này mà bạn chưa giải thích{where}?"]
        return hints[:3]


def apply_pass_rule(result: JudgeResult, rubric: Rubric) -> tuple[float, Verdict]:
    """BR-03: Đạt ⇔ S ≥ θ ∧ đủ mọi ý chính bắt buộc ∧ vượt ≥ k câu phản biện
    ∧ không còn quan niệm sai nghiêm trọng chưa được sửa. S = Σ wᵢ·sᵢ (mục 6.3.2).
    TC10: điểm 82 nhưng thiếu KP3 ⇒ FAILED."""
    pc = result.check_pass(rubric)
    return pc.total_score, pc.verdict
