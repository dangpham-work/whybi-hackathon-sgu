"""Các kiểu liệt kê – Hình 4.36 của đề cương. Dùng chung cho models, schemas và frontend (qua OpenAPI)."""

from enum import StrEnum


class Role(StrEnum):
    LECTURER = "LECTURER"
    STUDENT = "STUDENT"
    ADMIN = "ADMIN"


class MasteryState(StrEnum):
    """Trạng thái một ô của ma trận thành thạo (Hình 4.25, Bảng 4.8)."""

    LOCKED = "LOCKED"
    AVAILABLE = "AVAILABLE"
    IN_PROGRESS = "IN_PROGRESS"
    MASTERED = "MASTERED"
    NOT_PASSED = "NOT_PASSED"
    NEEDS_REVERIFY = "NEEDS_REVERIFY"


class SessionStatus(StrEnum):
    CREATED = "CREATED"
    EXPLAINING = "EXPLAINING"
    CHALLENGING = "CHALLENGING"
    EVALUATING = "EVALUATING"
    COMPLETED = "COMPLETED"
    ABANDONED = "ABANDONED"
    FLAGGED = "FLAGGED"


class InputMode(StrEnum):
    TEXT = "TEXT"
    VOICE = "VOICE"


class Speaker(StrEnum):
    STUDENT = "STUDENT"
    TUTEE = "TUTEE"


class TurnType(StrEnum):
    OPENING = "OPENING"
    EXPLANATION = "EXPLANATION"
    QUESTION = "QUESTION"
    ANSWER = "ANSWER"
    SYSTEM_NOTICE = "SYSTEM_NOTICE"


class QuestionStrategy(StrEnum):
    MISSING_KEY_POINT = "MISSING_KEY_POINT"
    MISCONCEPTION_PROBE = "MISCONCEPTION_PROBE"
    EDGE_CASE = "EDGE_CASE"
    TRANSFER = "TRANSFER"


class Verdict(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"


class TreeStatus(StrEnum):
    GENERATING = "GENERATING"
    FAILED = "FAILED"
    DRAFT = "DRAFT"
    EDITING = "EDITING"
    VALIDATING = "VALIDATING"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class HeatColor(StrEnum):
    GREY = "GREY"
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


class MatchStatus(StrEnum):
    PROPOSED = "PROPOSED"
    WAITING_OTHER = "WAITING_OTHER"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    EXPIRED = "EXPIRED"
    STUDIED = "STUDIED"
    VERIFIED = "VERIFIED"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    UNVERIFIED = "UNVERIFIED"


class CriterionCode(StrEnum):
    CORRECTNESS = "CORRECTNESS"
    COVERAGE = "COVERAGE"
    ESSENCE = "ESSENCE"
    ROBUSTNESS = "ROBUSTNESS"
    CLARITY = "CLARITY"


class FlagType(StrEnum):
    PASTE_SUSPECTED = "PASTE_SUSPECTED"
    JAILBREAK = "JAILBREAK"
    OFF_TOPIC = "OFF_TOPIC"
    LOW_STT_CONFIDENCE = "LOW_STT_CONFIDENCE"
    ANSWER_LEAK = "ANSWER_LEAK"


class BloomLevel(StrEnum):
    REMEMBER = "REMEMBER"
    UNDERSTAND = "UNDERSTAND"
    APPLY = "APPLY"
    ANALYZE = "ANALYZE"
    EVALUATE = "EVALUATE"
    CREATE = "CREATE"


class EdgeSource(StrEnum):
    AI = "AI"
    LECTURER = "LECTURER"


class DocumentStatus(StrEnum):
    UPLOADED = "UPLOADED"
    PARSING = "PARSING"
    PARSED = "PARSED"
    FAILED = "FAILED"


class RubricStatus(StrEnum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"


class ProviderKind(StrEnum):
    LLM = "LLM"
    STT = "STT"
    TTS = "TTS"
