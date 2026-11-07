"""C1-01 – hợp đồng phiên giảng lại (app/models/schemas/session.py).

Xong khi: schema import được; Thắng sinh kiểu TypeScript từ OpenAPI không lỗi.
Kiểm: validate, camelCase, ràng buộc giá trị, quy tắc Đạt BR-03 (TC10).
"""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.enums import (
    CriterionCode,
    FlagType,
    InputMode,
    MasteryState,
    QuestionStrategy,
    TurnType,
    Verdict,
)
from app.models.schemas.session import (
    DEFAULT_CRITERION_WEIGHTS,
    CriterionResult,
    CriterionScore,
    JudgeResult,
    MisconceptionFinding,
    PassCheck,
    Question,
    SessionCreated,
    SessionResult,
    SessionStart,
    Transcript,
    Turn,
    TurnReply,
)
from app.models.schemas.tree import KeyPointSchema, MisconceptionSchema, Rubric


def _scores(**override: float) -> list[CriterionScore]:
    base = {c: 80.0 for c in CriterionCode}
    base.update({CriterionCode(k.upper()): v for k, v in override.items()})
    return [CriterionScore(code=c, score=s, rationale="lý do") for c, s in base.items()]


def _rubric(**kw) -> Rubric:
    return Rubric(
        key_points=[
            KeyPointSchema(id="KP1", content="lưu địa chỉ"),
            KeyPointSchema(id="KP2", content="& và *"),
            KeyPointSchema(id="KP3", content="phép cộng con trỏ theo kiểu"),
            KeyPointSchema(id="KP4", content="ý phụ", is_required=False),
        ],
        misconceptions=[
            MisconceptionSchema(id="MC1", content="nhỏ"),
            MisconceptionSchema(id="MC2", content="free() làm con trỏ thành NULL", is_critical=True),
        ],
        **kw,
    )


def _judge(**kw) -> JudgeResult:
    data = dict(
        criteria=_scores(),
        covered_points=["KP1", "KP2", "KP3"],
        missing_points=[],
        misconceptions=[],
        passed_challenges=3,
        total_challenges=4,
    )
    data.update(kw)
    return JudgeResult(**data)


# --- SessionStart / Turn / Question -------------------------------------------------------------


def test_session_start_camelcase_and_defaults():
    nid = uuid4()
    s = SessionStart.model_validate({"nodeId": str(nid)})
    assert s.node_id == nid and s.input_mode == InputMode.TEXT and s.tts_enabled is False
    assert set(s.model_dump(by_alias=True)) == {"nodeId", "inputMode", "ttsEnabled", "peerMatchItemId"}


def test_turn_matches_example_5_4_4():
    body = {
        "turnType": "ANSWER",
        "inputMode": "VOICE",
        "text": "Con trỏ vẫn giữ địa chỉ cũ nên gọi là con trỏ treo…",
        "audioRef": "audio/7f3c/4.webm",
        "sttConfidence": 0.86,
        "transcriptEdited": False,
        "responseTimeMs": 41250,
    }
    t = Turn.model_validate(body)
    assert t.turn_type == TurnType.ANSWER and t.stt_confidence == 0.86
    assert t.model_dump(by_alias=True, exclude_unset=True) == body


@pytest.mark.parametrize(
    "bad",
    [
        {"text": ""},
        {"text": "   "},
        {"text": "x" * 20_001},
        {"text": "ok", "sttConfidence": 1.2},
        {"text": "ok", "pasteRatio": -0.1},
        {"text": "ok", "typingCps": -1},
        {"text": "ok", "responseTimeMs": -5},
        {"text": "ok", "turnType": "OPENING"},  # SV không gửi lượt mở đầu
        {"text": "ok", "inputMode": "VOICE"},  # giọng nói phải có audioRef
    ],
)
def test_turn_rejects_invalid(bad):
    with pytest.raises(ValidationError):
        Turn.model_validate(bad)


def test_question_constraints():
    q = Question(
        text="Nếu hai con trỏ cùng trỏ một ô thì sao?", strategy=QuestionStrategy.EDGE_CASE, target_point_id="SC1"
    )
    assert q.model_dump(by_alias=True)["targetPointId"] == "SC1"
    with pytest.raises(ValidationError):
        Question(text="")


def test_turn_reply_progress_bounds():
    TurnReply(status="CHALLENGING", questions_asked=2, questions_total=4)
    with pytest.raises(ValidationError):
        TurnReply(status="CHALLENGING", questions_asked=5, questions_total=4)


def test_session_created_has_opening():
    c = SessionCreated(session_id=uuid4(), status="EXPLAINING", opening=Question(text="Bạn giảng giúp mình nhé!"))
    assert c.model_dump(by_alias=True, mode="json")["opening"]["text"]


def test_transcript_word_confidence():
    t = Transcript(
        text="con trỏ phờ ri",
        confidence=0.7,
        words=[{"word": "con", "confidence": 0.95}, {"word": "phờ ri", "confidence": 0.4}],
        low_confidence_words=["phờ ri"],
        audio_ref="audio/x/1.webm",
        needs_confirmation=True,
    )
    assert t.model_dump(by_alias=True)["lowConfidenceWords"] == ["phờ ri"]
    with pytest.raises(ValidationError):
        Transcript(text="a", confidence=1.5, audio_ref="x")


# --- Điểm tiêu chí -----------------------------------------------------------------------------


def test_default_weights_sum_to_one_table_6_4():
    assert set(DEFAULT_CRITERION_WEIGHTS) == set(CriterionCode)
    assert sum(DEFAULT_CRITERION_WEIGHTS.values()) == pytest.approx(1.0)
    assert DEFAULT_CRITERION_WEIGHTS[CriterionCode.CORRECTNESS] == 0.25


def test_criterion_score_range():
    with pytest.raises(ValidationError):
        CriterionScore(code=CriterionCode.CLARITY, score=101)
    with pytest.raises(ValidationError):
        CriterionScore(code=CriterionCode.CLARITY, score=-1)


def test_criterion_result_score_not_above_max():
    CriterionResult(code=CriterionCode.CORRECTNESS, weight=0.25, score=22, max=25)
    with pytest.raises(ValidationError):
        CriterionResult(code=CriterionCode.CORRECTNESS, weight=0.25, score=26, max=25)
    with pytest.raises(ValidationError):
        CriterionResult(code=CriterionCode.CORRECTNESS, weight=1.5, score=1, max=25)


def test_criterion_result_from_score_scales_to_weight():
    r = CriterionResult.from_score(CriterionScore(code=CriterionCode.CORRECTNESS, score=88, rationale="ok"), 0.25)
    assert (r.score, r.max, r.weight, r.rationale) == (22, 25, 0.25, "ok")


# --- JudgeResult --------------------------------------------------------------------------------


def test_judge_result_requires_exactly_five_distinct_criteria():
    with pytest.raises(ValidationError):
        _judge(criteria=_scores()[:4])
    dup = _scores()
    dup[4] = CriterionScore(code=CriterionCode.CORRECTNESS, score=10)
    with pytest.raises(ValidationError):
        _judge(criteria=dup)


def test_judge_result_challenges_bounds():
    with pytest.raises(ValidationError):
        _judge(passed_challenges=5, total_challenges=4)
    with pytest.raises(ValidationError):
        _judge(passed_challenges=-1)


def test_judge_result_camelcase_and_misconception_shape():
    j = _judge(misconceptions=[{"id": "MC2", "corrected": True}])
    data = j.model_dump(by_alias=True)
    assert {"coveredPoints", "missingPoints", "passedChallenges", "totalChallenges", "judgeRuns"} <= set(data)
    assert data["misconceptions"] == [{"id": "MC2", "corrected": True, "evidence": None}]
    assert isinstance(j.misconceptions[0], MisconceptionFinding)


def test_total_score_is_weighted_sum():
    j = _judge(criteria=_scores(correctness=100, coverage=80, essence=50, robustness=70, clarity=90))
    # 0.25·100 + 0.25·80 + 0.20·50 + 0.20·70 + 0.10·90 = 25 + 20 + 10 + 14 + 9 = 78
    assert j.total_score() == pytest.approx(78)
    assert sum(c.score for c in j.weighted_criteria()) == pytest.approx(78)


# --- BR-03 --------------------------------------------------------------------------------------


def test_br03_pass_all_conditions():
    check = _judge(misconceptions=[{"id": "MC2", "corrected": True}]).check_pass(_rubric())
    assert isinstance(check, PassCheck)
    assert check.verdict == Verdict.PASSED and check.failed_conditions == []


def test_br03_tc10_high_score_but_missing_required_point_fails():
    j = _judge(
        criteria=_scores(correctness=82, coverage=82, essence=82, robustness=82, clarity=82),
        covered_points=["KP1", "KP2"],
        missing_points=["KP3"],
    )
    check = j.check_pass(_rubric())
    assert check.total_score == pytest.approx(82)
    assert check.verdict == Verdict.FAILED
    assert check.missing_required_points == ["KP3"]
    assert check.failed_conditions == ["REQUIRED_POINTS"]


def test_br03_optional_point_missing_still_passes():
    assert _judge(missing_points=["KP4"]).check_pass(_rubric()).verdict == Verdict.PASSED


def test_br03_below_threshold_fails():
    check = _judge(criteria=_scores(correctness=60, coverage=60, essence=60, robustness=60, clarity=60)).check_pass(
        _rubric()
    )
    assert check.verdict == Verdict.FAILED and check.failed_conditions == ["SCORE"]


def test_br03_threshold_from_rubric_is_inclusive():
    j = _judge(criteria=_scores(correctness=70, coverage=70, essence=70, robustness=70, clarity=70))
    assert j.check_pass(_rubric()).verdict == Verdict.PASSED
    assert j.check_pass(_rubric(pass_threshold=75)).verdict == Verdict.FAILED


def test_br03_not_enough_challenges_fails():
    check = _judge(passed_challenges=1).check_pass(_rubric())
    assert check.failed_conditions == ["CHALLENGES"]


def test_br03_uncorrected_critical_misconception_fails():
    check = _judge(misconceptions=[{"id": "MC2", "corrected": False}]).check_pass(_rubric())
    assert check.failed_conditions == ["CRITICAL_MISCONCEPTION"]
    assert check.uncorrected_critical_misconceptions == ["MC2"]


def test_br03_uncorrected_minor_misconception_still_passes():
    assert _judge(misconceptions=[{"id": "MC1", "corrected": False}]).check_pass(_rubric()).verdict == Verdict.PASSED


def test_br03_override_threshold_and_k():
    j = _judge(passed_challenges=2)
    assert j.check_pass(_rubric(), pass_threshold=90).verdict == Verdict.FAILED
    assert j.check_pass(_rubric(), min_passed_challenges=3).failed_conditions == ["CHALLENGES"]


# --- SessionResult ------------------------------------------------------------------------------


def _result(**kw) -> SessionResult:
    data = dict(
        session_id=uuid4(),
        student_id=uuid4(),
        node_id=uuid4(),
        class_id=uuid4(),
        state=MasteryState.MASTERED,
        verdict=Verdict.PASSED,
        total_score=78,
        criteria=[CriterionResult(code=CriterionCode.CORRECTNESS, weight=0.25, score=22, max=25)],
    )
    data.update(kw)
    return SessionResult(**data)


def test_session_result_camelcase_keys():
    data = _result(flags=[FlagType.PASTE_SUSPECTED]).model_dump(by_alias=True, mode="json")
    for key in ("sessionId", "studentId", "nodeId", "classId", "state", "verdict", "totalScore", "criteria", "flags"):
        assert key in data
    assert data["flags"] == ["PASTE_SUSPECTED"]
    assert SessionResult.model_validate(data).flags == [FlagType.PASTE_SUSPECTED]


@pytest.mark.parametrize("bad", [{"total_score": 101}, {"total_score": -1}, {"pass_threshold": 150}])
def test_session_result_score_bounds(bad):
    with pytest.raises(ValidationError):
        _result(**bad)


def test_session_result_rejects_unknown_flag():
    with pytest.raises(ValidationError):
        _result(flags=["HACKED"])


# --- OpenAPI (để Thắng chạy npm run gen:api) ----------------------------------------------------


def test_openapi_exposes_session_schemas():
    from app.main import app

    schemas = app.openapi()["components"]["schemas"]
    for name in (
        "SessionStart",
        "SessionCreated",
        "Turn",
        "TurnReply",
        "Question",
        "Transcript",
        "SessionResult",
        "CriterionResult",
    ):
        assert name in schemas, name
    props = schemas["SessionResult"]["properties"]
    assert "totalScore" in props and "studentId" in props
