"""Hợp đồng API quản trị – FR-AD-03, 04, 06, 07. Chủ: Long (C2-18). `AIConfig` nằm ở api/admin.py (Đăng)."""

import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.models.enums import Role
from app.models.schemas.common import ApiModel

_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def valid_email(value: str) -> str:
    value = value.strip().lower()
    if not _EMAIL.fullmatch(value) or len(value) > 150:
        raise ValueError("email không hợp lệ")
    return value


class UserOut(ApiModel):
    id: UUID
    full_name: str
    email: str
    role: Role
    is_active: bool
    student_code: str | None = None
    cohort: str | None = None
    created_at: datetime


class UserCreate(ApiModel):
    full_name: str = Field(min_length=1, max_length=120)
    email: str
    role: Role
    student_code: str | None = Field(None, max_length=20)  # bắt buộc khi role = STUDENT
    cohort: str | None = Field(None, max_length=20)

    _email = field_validator("email")(valid_email)


class UserPatch(ApiModel):
    full_name: str | None = Field(None, min_length=1, max_length=120)
    is_active: bool | None = None


class CreatedUser(ApiModel):
    """Mật khẩu ban đầu chỉ trả đúng một lần – QTV chuyển cho người dùng, không xem lại được."""

    user: UserOut
    password: str


class RowIssue(ApiModel):
    row: int  # số dòng trong tệp CSV (dòng tiêu đề là 1)
    reason: str


class ImportedStudent(ApiModel):
    row: int
    student_code: str
    full_name: str
    email: str
    password: str


class ImportResult(ApiModel):
    created: list[ImportedStudent]
    skipped: list[RowIssue]  # đã có tài khoản (cùng email hoặc MSSV) – không đụng tới
    errors: list[RowIssue]  # dòng sai dữ liệu – không tạo


class CourseIn(ApiModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=200)
    credits: int | None = Field(None, ge=0, le=20)
    description: str | None = None


class CourseOut(CourseIn):
    id: UUID


class QuotaIn(ApiModel):
    """`null` = không giới hạn loại đó; cả hai null = bỏ hạn mức."""

    scope: Literal["CLASS", "STUDENT"]
    scope_id: UUID
    token_limit: int | None = Field(None, ge=0)
    audio_minutes_limit: int | None = Field(None, ge=0)


class QuotaOut(QuotaIn):
    name: str | None = None  # tên lớp / họ tên SV
    tokens_used: int = 0
    audio_minutes_used: float = 0.0


class ClassLiteOut(ApiModel):
    """Danh sách gọn để QTV chọn lớp khi đặt hạn mức, thay cho gõ tay UUID (C2-24)."""

    id: UUID
    name: str


class UsageStatsOut(ApiModel):
    """Token / phút ghi âm đã dùng, cộng theo provider + model LLM đang/đã cấu hình (C2-24, bổ sung FR-AD-06)."""

    provider: str
    model: str
    tokens_used: int
    audio_minutes_used: float
    session_count: int


class FlagOut(ApiModel):
    id: UUID
    session_id: UUID
    turn_id: UUID | None = None
    class_id: UUID
    student_id: UUID
    student_name: str = ""
    type: str
    severity: str
    detail: str | None = None
    resolved: bool
    resolved_by: UUID | None = None
    created_at: datetime


class AuditLogOut(ApiModel):
    id: int
    user_id: UUID | None = None
    action: str
    entity: str
    entity_id: UUID | None = None
    payload: dict | None = None
    created_at: datetime
