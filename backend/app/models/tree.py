"""ERD chi tiết (2) – Hình 5.5: cây kỹ năng và rubric. Ràng buộc DAG: mục 5.2.5."""

import uuid
from datetime import datetime

from sqlalchemy import (
    REAL,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPk, created_at_col


class SkillTree(UUIDPk, Base):
    __tablename__ = "skill_trees"
    class_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("class_sections.id", ondelete="CASCADE"), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    published_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tree_versions.id", use_alter=True, name="fk_skill_trees_published_version")
    )
    created_at: Mapped[datetime] = created_at_col()


class TreeVersion(UUIDPk, Base):
    __tablename__ = "tree_versions"
    __table_args__ = (UniqueConstraint("tree_id", "version_no"),)
    tree_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("skill_trees.id", ondelete="CASCADE"))
    version_no: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))  # TreeStatus (Hình 4.29)
    change_note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = created_at_col()
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ConceptNode(UUIDPk, Base):
    __tablename__ = "concept_nodes"
    __table_args__ = (UniqueConstraint("version_id", "key"),)
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tree_versions.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(String(64))  # ổn định giữa các phiên bản (di chuyển trạng thái SV)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    chapter_ref: Mapped[str | None] = mapped_column(String(100))
    bloom_level: Mapped[str] = mapped_column(String(16))  # BloomLevel
    position_x: Mapped[float | None] = mapped_column(REAL)
    position_y: Mapped[float | None] = mapped_column(REAL)
    min_challenges: Mapped[int] = mapped_column(SmallInteger, default=3)


class PrerequisiteEdge(UUIDPk, Base):
    __tablename__ = "prerequisite_edges"
    __table_args__ = (
        UniqueConstraint("version_id", "from_node_id", "to_node_id"),
        CheckConstraint("from_node_id <> to_node_id", name="no_self_loop"),  # BR-01
    )
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tree_versions.id", ondelete="CASCADE"))
    from_node_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("concept_nodes.id", ondelete="CASCADE"))
    to_node_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("concept_nodes.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(10))  # EdgeSource: AI / LECTURER
    confidence: Mapped[float | None] = mapped_column(REAL)


class Rubric(UUIDPk, Base):
    __tablename__ = "rubrics"
    node_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("concept_nodes.id", ondelete="CASCADE"), unique=True)
    pass_threshold: Mapped[int] = mapped_column(SmallInteger, default=70)
    status: Mapped[str] = mapped_column(String(16), default="DRAFT")  # RubricStatus
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RubricCriterion(UUIDPk, Base):
    __tablename__ = "rubric_criteria"
    rubric_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rubrics.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(16))  # CriterionCode
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    weight: Mapped[float] = mapped_column(Numeric(4, 2))
    max_score: Mapped[int] = mapped_column(SmallInteger)


class KeyPoint(UUIDPk, Base):
    __tablename__ = "key_points"
    node_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("concept_nodes.id", ondelete="CASCADE"))
    content: Mapped[str] = mapped_column(Text)
    is_required: Mapped[bool] = mapped_column(Boolean, default=True)
    source_chunk_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("document_chunks.id", ondelete="SET NULL"))


class Misconception(UUIDPk, Base):
    __tablename__ = "misconceptions"
    node_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("concept_nodes.id", ondelete="CASCADE"))
    content: Mapped[str] = mapped_column(Text)
    probe_question: Mapped[str | None] = mapped_column(Text)
    is_critical: Mapped[bool] = mapped_column(Boolean, default=False)


class ChallengeScenario(UUIDPk, Base):
    __tablename__ = "challenge_scenarios"
    node_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("concept_nodes.id", ondelete="CASCADE"))
    scenario: Mapped[str] = mapped_column(Text)
    bloom_level: Mapped[str] = mapped_column(String(16))
    expected_points: Mapped[str | None] = mapped_column(Text)
