"""ERD chi tiết (3) – Hình 5.6: phiên giảng lại, đánh giá và thành thạo (Bảng 5.3–5.6)."""

import uuid
from datetime import datetime

from sqlalchemy import (
    REAL,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPk, created_at_col, utcnow


class TeachingSession(UUIDPk, Base):
    __tablename__ = "teaching_sessions"
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.user_id"))
    node_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("concept_nodes.id"))
    class_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("class_sections.id"))
    input_mode: Mapped[str] = mapped_column(String(8))  # InputMode lúc bắt đầu
    status: Mapped[str] = mapped_column(String(16))  # SessionStatus (Hình 4.26)
    attempt_no: Mapped[int] = mapped_column(SmallInteger, default=1)
    is_peer_followup: Mapped[bool] = mapped_column(Boolean, default=False)
    peer_match_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("peer_match_items.id", use_alter=True, name="fk_teaching_sessions_peer_item")
    )
    tts_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SessionTurn(UUIDPk, Base):
    __tablename__ = "session_turns"
    __table_args__ = (UniqueConstraint("session_id", "turn_no"),)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teaching_sessions.id", ondelete="CASCADE"))
    turn_no: Mapped[int] = mapped_column(SmallInteger)
    speaker: Mapped[str] = mapped_column(String(8))  # Speaker
    turn_type: Mapped[str] = mapped_column(String(16))  # TurnType
    content: Mapped[str | None] = mapped_column(Text)
    input_mode: Mapped[str] = mapped_column(String(8))
    audio_url: Mapped[str | None] = mapped_column(Text)
    stt_confidence: Mapped[float | None] = mapped_column(REAL)
    transcript_edited: Mapped[bool | None] = mapped_column(Boolean)
    paste_ratio: Mapped[float | None] = mapped_column(REAL)
    response_time_ms: Mapped[int | None] = mapped_column(Integer)
    strategy: Mapped[str | None] = mapped_column(String(24))  # QuestionStrategy
    created_at: Mapped[datetime] = created_at_col()


class Evaluation(UUIDPk, Base):
    __tablename__ = "evaluations"
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teaching_sessions.id", ondelete="CASCADE"), unique=True)
    total_score: Mapped[float] = mapped_column(Numeric(5, 2))
    verdict: Mapped[str] = mapped_column(String(8))  # Verdict
    covered_points: Mapped[list | None] = mapped_column(JSONB)
    missing_points: Mapped[list | None] = mapped_column(JSONB)
    detected_misconceptions: Mapped[list | None] = mapped_column(JSONB)
    feedback: Mapped[str | None] = mapped_column(Text)  # không chứa đáp án
    judge_runs: Mapped[int] = mapped_column(SmallInteger, default=2)
    created_at: Mapped[datetime] = created_at_col()


class CriterionScore(UUIDPk, Base):
    __tablename__ = "criterion_scores"
    evaluation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evaluations.id", ondelete="CASCADE"))
    criterion_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rubric_criteria.id"))
    score: Mapped[float] = mapped_column(Numeric(5, 2))
    rationale: Mapped[str | None] = mapped_column(Text)


class MasteryRecord(UUIDPk, Base):
    """Một ô của ma trận thành thạo M[SV × Nút] – cấu trúc dữ liệu trung tâm (mục 5.2.6)."""

    __tablename__ = "mastery_records"
    __table_args__ = (
        UniqueConstraint("student_id", "node_id"),
        Index("ix_mastery_class_node_state", "class_id", "node_id", "state"),
    )
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.user_id", ondelete="CASCADE"))
    node_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("concept_nodes.id", ondelete="CASCADE"))
    class_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("class_sections.id", ondelete="CASCADE"))
    state: Mapped[str] = mapped_column(String(16))  # MasteryState
    best_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0)
    last_session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teaching_sessions.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SecurityFlag(UUIDPk, Base):
    __tablename__ = "security_flags"
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teaching_sessions.id", ondelete="CASCADE"))
    turn_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("session_turns.id", ondelete="SET NULL"))
    type: Mapped[str] = mapped_column(String(24))  # FlagType
    severity: Mapped[str] = mapped_column(String(8))
    detail: Mapped[str | None] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = created_at_col()
