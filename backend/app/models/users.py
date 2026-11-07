"""ERD chi tiết (1) – Hình 5.4: người dùng, lớp học, tài liệu và thông báo."""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CHAR,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPk, created_at_col, utcnow


class User(UUIDPk, Base):
    __tablename__ = "users"
    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(150), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16))  # Role: LECTURER / STUDENT / ADMIN
    avatar_url: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = created_at_col()


class Lecturer(Base):
    __tablename__ = "lecturers"
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    faculty: Mapped[str | None] = mapped_column(String(120))
    academic_title: Mapped[str | None] = mapped_column(String(40))


class Student(Base):
    __tablename__ = "students"
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    student_code: Mapped[str] = mapped_column(String(20), unique=True)
    cohort: Mapped[str | None] = mapped_column(String(20))


class Course(UUIDPk, Base):
    __tablename__ = "courses"
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    credits: Mapped[int | None] = mapped_column(SmallInteger)
    description: Mapped[str | None] = mapped_column(Text)


class ClassSection(UUIDPk, Base):
    __tablename__ = "class_sections"
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id"))
    lecturer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lecturers.user_id"))
    name: Mapped[str] = mapped_column(String(120))
    semester: Mapped[str] = mapped_column(String(20))
    join_code: Mapped[str] = mapped_column(CHAR(8), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")
    pass_threshold: Mapped[int] = mapped_column(SmallInteger, default=70)  # BR-03
    color_thresholds: Mapped[dict] = mapped_column(JSONB, default=lambda: {"green": 0.7, "yellow": 0.4})  # BR-06
    min_sample: Mapped[int] = mapped_column(SmallInteger, default=5)  # BR-06
    created_at: Mapped[datetime] = created_at_col()


class Enrollment(UUIDPk, Base):
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("class_id", "student_id"),)
    class_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("class_sections.id", ondelete="CASCADE"))
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.user_id", ondelete="CASCADE"))
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    peer_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)  # FR-PM-01


class SyllabusDocument(UUIDPk, Base):
    __tablename__ = "syllabus_documents"
    class_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("class_sections.id", ondelete="CASCADE"))
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    file_url: Mapped[str] = mapped_column(Text)
    file_type: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(16), default="UPLOADED")  # DocumentStatus
    page_count: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DocumentChunk(UUIDPk, Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        Index(
            "ix_document_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("syllabus_documents.id", ondelete="CASCADE"))
    chapter: Mapped[str | None] = mapped_column(String(200))
    section_title: Mapped[str | None] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(768))  # chỉ mục HNSW cosine – mục 5.2.7
    page_from: Mapped[int | None] = mapped_column(Integer)
    page_to: Mapped[int | None] = mapped_column(Integer)


class Notification(UUIDPk, Base):
    __tablename__ = "notifications"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = created_at_col()
