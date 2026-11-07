"""HỢP ĐỒNG DỮ LIỆU #2 – phiên giảng lại (Bảng 7 kế hoạch phân công).
Người chốt: Đăng + Long (C1-01) · Bên dùng: Long, Thắng, Quyền · Hạn: H1.
Ví dụ JSON tham chiếu: mục 5.4.4 của đề cương.

Quy ước điểm (chốt ở C1-01):
- Judge (LLM) cho mỗi tiêu chí điểm 0–100 → `CriterionScore` (Phụ lục A.2).
- Kết quả trả SV / sự kiện quy về điểm có trọng số → `CriterionResult` (score ≤ max = weight·100),
  khớp ví dụ 5.4.4 ({"code": "CORRECTNESS", "weight": 0.25, "score": 22, "max": 25}).
- Tổng điểm S = Σ wᵢ·sᵢ ∈ [0, 100] (mục 6.3.2); kết luận theo BR-03 qua `JudgeResult.check_pass`.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field, field_validator, model_validator

from app.models.enums import (
    CriterionCode,
    FlagType,
    InputMode,
    MasteryState,
    QuestionStrategy,
    SessionStatus,
    TurnType,
    Verdict,
)
from app.models.schemas.common import ApiModel
from app.models.schemas.tree import Rubric

# Bảng 6.4 – trọng số mặc định (Σ = 1). GV có thể chỉnh qua cấu hình lớp (C2-17).
DEFAULT_CRITERION_WEIGHTS: dict[CriterionCode, float] = {
    CriterionCode.CORRECTNESS: 0.25,
    CriterionCode.COVERAGE: 0.25,
    CriterionCode.ESSENCE: 0.20,
    CriterionCode.ROBUSTNESS: 0.20,
    CriterionCode.CLARITY: 0.10,
}

MAX_TURN_CHARS = 20_000  # ~ 3 phút nói / một lời giảng dài; chặn payload bất thường


class SessionStart(ApiModel):
    """POST /sessions"""

    node_id: UUID
    input_mode: InputMode = InputMode.TEXT
    tts_enabled: bool = False
    peer_match_item_id: UUID | None = None  # phiên xác nhận lại sau học cặp (FR-PM-07)


class Question(ApiModel):
    """Câu hỏi của Tutee (kênh session:{id} → session.question; cũng là câu mở đầu)."""

    text: str = Field(min_length=1, max_length=1000)
    strategy: QuestionStrategy | None = None  # None ⇔ câu mở đầu (OPENING)
    target_point_id: str | None = None  # "KP3" / "MC2" / "SC1"
    audio_url: str | None = None  # TTS (FR-TB-10)
    deadline: datetime | None = None  # FR-TB-11


class SessionCreated(ApiModel):
    """Trả về của POST /sessions (201)."""

    session_id: UUID
    status: SessionStatus
    opening: Question


class Turn(ApiModel):
    """POST /sessions/{id}/turns – lời giảng (EXPLANATION) hoặc câu trả lời (ANSWER) của SV."""

    turn_type: Literal[TurnType.EXPLANATION, TurnType.ANSWER] = TurnType.EXPLANATION
    input_mode: InputMode = InputMode.TEXT
    text: str = Field(min_length=1, max_length=MAX_TURN_CHARS)
    audio_ref: str | None = None  # bắt buộc khi inputMode = VOICE
    stt_confidence: float | None = Field(None, ge=0, le=1)
    transcript_edited: bool = False
    paste_ratio: float | None = Field(None, ge=0, le=1)  # FR-TB-04: tỉ lệ ký tự đến từ sự kiện dán
    typing_cps: float | None = Field(None, ge=0)  # ký tự / giây
    response_time_ms: int | None = Field(None, ge=0)

    @field_validator("text")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text không được rỗng")
        return v

    @model_validator(mode="after")
    def _voice_needs_audio(self) -> "Turn":
        if self.input_mode == InputMode.VOICE and not self.audio_ref:
            raise ValueError("inputMode=VOICE cần audioRef (POST /sessions/{id}/audio trước)")
        return self


class TurnReply(ApiModel):
    """Trả về của POST /sessions/{id}/turns và /timeout."""

    status: SessionStatus
    question: Question | None = None  # None khi vòng phản biện kết thúc
    notice: str | None = None  # phản hồi trung lập khi Guard gắn cờ
    questions_asked: int = Field(0, ge=0)
    questions_total: int = Field(0, ge=0)

    @model_validator(mode="after")
    def _progress(self) -> "TurnReply":
        if self.questions_total and self.questions_asked > self.questions_total:
            raise ValueError("questionsAsked không được vượt questionsTotal")
        return self


class WordConfidence(ApiModel):
    word: str
    confidence: float = Field(ge=0, le=1)


class Transcript(ApiModel):
    """POST /sessions/{id}/audio → bản chép lời (FR-TB-06, FR-TB-07)."""

    text: str
    confidence: float = Field(ge=0, le=1)
    words: list[WordConfidence] = []
    low_confidence_words: list[str] = []
    audio_ref: str
    needs_confirmation: bool = False  # confidence < STT_MIN_CONFIDENCE ⇒ SV-05


# --- Chấm điểm (mục 6.3) ----------------------------------------------------------------------


class CriterionScore(ApiModel):
    """Điểm Judge cho MỘT tiêu chí, thang 0–100 (Phụ lục A.2)."""

    code: CriterionCode
    score: float = Field(ge=0, le=100)
    rationale: str | None = None
    evidence: str | None = None  # câu trích nguyên văn của SV


class CriterionResult(ApiModel):
    """Điểm có trọng số hiển thị cho SV / GV: score ∈ [0, max], max = weight·100 (ví dụ 5.4.4)."""

    code: CriterionCode
    weight: float = Field(ge=0, le=1)
    score: float = Field(ge=0)
    max: float = Field(gt=0)
    rationale: str | None = None

    @model_validator(mode="after")
    def _score_le_max(self) -> "CriterionResult":
        if self.score > self.max + 1e-9:
            raise ValueError("score không được vượt max")
        return self

    @classmethod
    def from_score(cls, s: CriterionScore, weight: float) -> "CriterionResult":
        return cls(
            code=s.code,
            weight=weight,
            score=round(s.score * weight, 2),
            max=round(weight * 100, 2),
            rationale=s.rationale,
        )


class MisconceptionFinding(ApiModel):
    """Quan niệm sai Judge phát hiện; `id` theo rubric ("MC2")."""

    id: str
    corrected: bool = False  # SV đã tự sửa trong phiên
    evidence: str | None = None


PassCondition = Literal["SCORE", "REQUIRED_POINTS", "CHALLENGES", "CRITICAL_MISCONCEPTION"]


class PassCheck(ApiModel):
    """Kết quả áp BR-03 – lưu kèm để GV-08 thấy vì sao Đạt / Chưa đạt."""

    verdict: Verdict
    total_score: float = Field(ge=0, le=100)
    pass_threshold: int = Field(ge=0, le=100)
    missing_required_points: list[str] = []
    passed_challenges: int = Field(ge=0)
    min_passed_challenges: int = Field(ge=0)
    uncorrected_critical_misconceptions: list[str] = []
    failed_conditions: list[PassCondition] = []


_JUDGE_EXAMPLE = {
    "criteria": [
        {"code": "CORRECTNESS", "score": 88, "rationale": "Không có phát biểu sai", "evidence": None},
        {"code": "COVERAGE", "score": 80, "rationale": "Đủ ý bắt buộc", "evidence": None},
        {"code": "ESSENCE", "score": 75, "rationale": "Giải thích được cơ chế", "evidence": None},
        {"code": "ROBUSTNESS", "score": 70, "rationale": "Vượt 3/4 câu", "evidence": None},
        {"code": "CLARITY", "score": 70, "rationale": "Hiểu được", "evidence": None},
    ],
    "coveredPoints": ["KP1", "KP2", "KP3"],
    "missingPoints": [],
    "misconceptions": [{"id": "MC2", "corrected": True, "evidence": None}],
    "passedChallenges": 3,
    "totalChallenges": 4,
    "strengths": ["Giải thích đúng con trỏ treo khi bị hỏi về free()"],
    "reviewHints": ["Vì sao con trỏ cần có kiểu dữ liệu? Thử nghĩ về phép cộng con trỏ."],
    "judgeRuns": 1,
}


class JudgeResult(ApiModel):
    """Đầu ra của Judge (mục 6.3, Phụ lục A.2) trước khi áp BR-03. Cũng là schema ép JSON cho LLM."""

    model_config = ConfigDict(json_schema_extra={"examples": [_JUDGE_EXAMPLE]})

    criteria: list[CriterionScore] = Field(min_length=5, max_length=5)  # đúng 5 tiêu chí, mỗi mã một lần
    covered_points: list[str]  # id ý chính đã nêu ("KP1")
    missing_points: list[str]
    misconceptions: list[MisconceptionFinding] = []
    passed_challenges: int = Field(ge=0)
    total_challenges: int | None = Field(None, ge=0)
    strengths: list[str] = []
    review_hints: list[str] = []  # câu hỏi gợi mở, KHÔNG chứa đáp án (mục 6.3.4)
    judge_runs: int = Field(1, ge=1)  # số lần chấm đã gộp (mục 6.3.3)

    @field_validator("criteria")
    @classmethod
    def _distinct_codes(cls, v: list[CriterionScore]) -> list[CriterionScore]:
        if {c.code for c in v} != set(CriterionCode):
            raise ValueError("criteria phải có đủ 5 mã CORRECTNESS, COVERAGE, ESSENCE, ROBUSTNESS, CLARITY")
        return v

    @model_validator(mode="after")
    def _challenges(self) -> "JudgeResult":
        if self.total_challenges is not None and self.passed_challenges > self.total_challenges:
            raise ValueError("passedChallenges không được vượt totalChallenges")
        return self

    def score_of(self, code: CriterionCode) -> float:
        return next(c.score for c in self.criteria if c.code == code)

    def total_score(self, weights: dict[CriterionCode, float] | None = None) -> float:
        """S = Σ wᵢ·sᵢ (mục 6.3.2)."""
        w = weights or DEFAULT_CRITERION_WEIGHTS
        return round(sum(w[c.code] * c.score for c in self.criteria), 2)

    def weighted_criteria(self, weights: dict[CriterionCode, float] | None = None) -> list[CriterionResult]:
        w = weights or DEFAULT_CRITERION_WEIGHTS
        order = list(CriterionCode)
        return [
            CriterionResult.from_score(c, w[c.code]) for c in sorted(self.criteria, key=lambda c: order.index(c.code))
        ]

    def check_pass(
        self,
        rubric: Rubric,
        *,
        pass_threshold: int | None = None,
        min_passed_challenges: int | None = None,
        weights: dict[CriterionCode, float] | None = None,
    ) -> PassCheck:
        """BR-03: Đạt ⇔ S ≥ θ ∧ đủ mọi ý chính bắt buộc ∧ vượt ≥ k câu phản biện
        ∧ không còn quan niệm sai nghiêm trọng chưa được sửa. θ, k mặc định lấy từ rubric (70, 2);
        tham số ghi đè dùng cho cấu hình lớp (C1-15 / C2-17)."""
        theta = rubric.pass_threshold if pass_threshold is None else pass_threshold
        k = rubric.min_passed_challenges if min_passed_challenges is None else min_passed_challenges
        total = self.total_score(weights)

        covered = set(self.covered_points) - set(self.missing_points)
        missing_required = [kp.id for kp in rubric.key_points if kp.is_required and kp.id not in covered]
        critical_ids = {m.id for m in rubric.misconceptions if m.is_critical}
        uncorrected = [m.id for m in self.misconceptions if m.id in critical_ids and not m.corrected]

        failed: list[PassCondition] = []
        if total < theta:
            failed.append("SCORE")
        if missing_required:
            failed.append("REQUIRED_POINTS")
        if self.passed_challenges < k:
            failed.append("CHALLENGES")
        if uncorrected:
            failed.append("CRITICAL_MISCONCEPTION")

        return PassCheck(
            verdict=Verdict.FAILED if failed else Verdict.PASSED,
            total_score=total,
            pass_threshold=theta,
            missing_required_points=missing_required,
            passed_challenges=self.passed_challenges,
            min_passed_challenges=k,
            uncorrected_critical_misconceptions=uncorrected,
            failed_conditions=failed,
        )


class SessionResult(ApiModel):
    """GET /sessions/{id}/result và payload sự kiện session.completed (Redis Pub/Sub).
    Bên nghe: MasteryService (Long, C2-10) đọc studentId, nodeId, classId, verdict, flags, isPeerFollowup."""

    session_id: UUID
    student_id: UUID
    node_id: UUID
    class_id: UUID
    state: MasteryState  # trạng thái ô ma trận sau phiên
    verdict: Verdict
    total_score: float = Field(ge=0, le=100)
    pass_threshold: int = Field(70, ge=0, le=100)
    criteria: list[CriterionResult]
    strengths: list[str] = []
    review_hints: list[str] = []  # câu hỏi gợi mở, KHÔNG chứa đáp án
    source_pages: list[int] = []
    unlocked_nodes: list[str] = []
    flags: list[FlagType] = []
    is_peer_followup: bool = False
    detected_misconceptions: list[str] = []
    completed_at: datetime | None = None
