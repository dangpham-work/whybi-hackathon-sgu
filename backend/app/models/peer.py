"""ERD chi tiết (4) – Hình 5.7: thống kê bản đồ nhiệt, ghép cặp, cấu hình và nhật ký."""

import uuid
from datetime import datetime

from sqlalchemy import (
    REAL,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPk, created_at_col, utcnow


class ClassNodeStat(UUIDPk, Base):
    """Chỉ số tổng hợp theo cột của ma trận – Bảng 5.7."""

    __tablename__ = "class_node_stats"
    __table_args__ = (UniqueConstraint("class_id", "node_id"),)
    class_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("class_sections.id", ondelete="CASCADE"))
    node_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("concept_nodes.id", ondelete="CASCADE"))
    enrolled_count: Mapped[int] = mapped_column(Integer, default=0)
    attempted_count: Mapped[int] = mapped_column(Integer, default=0)
    passed_count: Mapped[int] = mapped_column(Integer, default=0)
    pass_rate: Mapped[float | None] = mapped_column(REAL)
    avg_attempts: Mapped[float | None] = mapped_column(REAL)
    color: Mapped[str] = mapped_column(String(8), default="GREY")  # HeatColor
    top_misconceptions: Mapped[list | None] = mapped_column(JSONB)
    root_cause_node_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("concept_nodes.id", ondelete="SET NULL"))
    root_cause_score: Mapped[float | None] = mapped_column(REAL)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class MatchingRound(UUIDPk, Base):
    __tablename__ = "matching_rounds"
    class_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("class_sections.id", ondelete="CASCADE"))
    trigger_type: Mapped[str] = mapped_column(String(12))  # MANUAL / SCHEDULED
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    algorithm: Mapped[str] = mapped_column(String(24), default="BLOSSOM")
    participant_count: Mapped[int | None] = mapped_column(Integer)
    total_weight: Mapped[float | None] = mapped_column(REAL)
    created_at: Mapped[datetime] = created_at_col()


class PeerMatch(UUIDPk, Base):
    __tablename__ = "peer_matches"
    round_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("matching_rounds.id", ondelete="CASCADE"))
    student_a_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.user_id"))
    student_b_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.user_id"))
    weight: Mapped[float] = mapped_column(REAL)
    status: Mapped[str] = mapped_column(String(24))  # MatchStatus (Hình 4.30)
    accepted_by_a: Mapped[bool] = mapped_column(Boolean, default=False)
    accepted_by_b: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()


class PeerMatchItem(UUIDPk, Base):
    __tablename__ = "peer_match_items"
    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("peer_matches.id", ondelete="CASCADE"))
    teacher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.user_id"))
    learner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.user_id"))
    node_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("concept_nodes.id"))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AIProviderConfig(UUIDPk, Base):
    __tablename__ = "ai_provider_configs"
    kind: Mapped[str] = mapped_column(String(8))  # ProviderKind: LLM / STT / TTS
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(80))
    params: Mapped[dict | None] = mapped_column(JSONB)
    quota: Mapped[dict | None] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(40))
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    payload: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_col()
