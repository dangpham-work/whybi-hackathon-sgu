"""Toàn bộ 30 bảng của ERD (Hình 5.3). Import ở đây để Alembic thấy metadata.
Chỉ Long tạo migration (quy tắc Git mục 8.3)."""

from app.db.base import Base
from app.models.peer import (
    AIProviderConfig,
    AuditLog,
    ClassNodeStat,
    MatchingRound,
    PeerMatch,
    PeerMatchItem,
)
from app.models.session import (
    CriterionScore,
    Evaluation,
    MasteryRecord,
    SecurityFlag,
    SessionTurn,
    TeachingSession,
)
from app.models.tree import (
    ChallengeScenario,
    ConceptNode,
    KeyPoint,
    Misconception,
    PrerequisiteEdge,
    Rubric,
    RubricCriterion,
    SkillTree,
    TreeVersion,
)
from app.models.users import (
    ClassSection,
    Course,
    DocumentChunk,
    Enrollment,
    Lecturer,
    Notification,
    Student,
    SyllabusDocument,
    User,
)

__all__ = [
    "Base",
    "User",
    "Lecturer",
    "Student",
    "Course",
    "ClassSection",
    "Enrollment",
    "SyllabusDocument",
    "DocumentChunk",
    "Notification",
    "SkillTree",
    "TreeVersion",
    "ConceptNode",
    "PrerequisiteEdge",
    "Rubric",
    "RubricCriterion",
    "KeyPoint",
    "Misconception",
    "ChallengeScenario",
    "TeachingSession",
    "SessionTurn",
    "Evaluation",
    "CriterionScore",
    "MasteryRecord",
    "SecurityFlag",
    "ClassNodeStat",
    "MatchingRound",
    "PeerMatch",
    "PeerMatchItem",
    "AIProviderConfig",
    "AuditLog",
]
