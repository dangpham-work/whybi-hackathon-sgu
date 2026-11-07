"""Quản trị – FR-AD-03…08. Chủ: Long (C2-18, C2-19), Đăng (C1-02: ai-config)."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.ai.gateway import configure_llm
from app.api.deps import Admin, AnyUser, CurrentUser, LecturerOrAdmin
from app.core.errors import AppError, NotImplementedYet
from app.db.session import get_db
from app.models.enums import ProviderKind, Role
from app.models.schemas.admin import (
    AuditLogOut,
    CourseIn,
    CourseOut,
    CreatedUser,
    FlagOut,
    ImportResult,
    QuotaIn,
    QuotaOut,
    UserCreate,
    UserOut,
    UserPatch,
)
from app.models.schemas.common import ApiModel
from app.services.admin import MAX_CSV_BYTES, AdminService
from app.services.quota import QuotaService

router = APIRouter(tags=["admin"])


class ProviderConfig(ApiModel):
    kind: ProviderKind
    provider: str
    model: str
    fallback_provider: str | None = None
    fallback_model: str | None = None
    params: dict = {}
    quota: dict = {}


class AIConfig(ApiModel):
    llm: ProviderConfig
    stt: ProviderConfig
    tts: ProviderConfig
    audio_retention_days: int = 30


@router.get("/admin/flags", response_model=list[FlagOut])
def list_flags(
    resolved: bool = False, user: CurrentUser = LecturerOrAdmin, db: Session = Depends(get_db)
) -> list[FlagOut]:
    """Cờ vi phạm (FR-AD-07), mới nhất trước. QTV thấy mọi lớp; GV chỉ thấy cờ của lớp mình phụ trách."""
    return AdminService(db).list_flags(user, resolved)


@router.post("/admin/flags/{flag_id}/resolve", response_model=FlagOut)
def resolve_flag(flag_id: UUID, user: CurrentUser = LecturerOrAdmin, db: Session = Depends(get_db)) -> FlagOut:
    """Đánh dấu đã xử lý và ghi nhật ký. Cờ không tồn tại hoặc thuộc lớp khác (với GV) ⇒ 404 FLAG_NOT_FOUND."""
    return AdminService(db).resolve_flag(user, flag_id)


@router.get("/admin/audit-logs", response_model=list[AuditLogOut])
def list_audit_logs(
    limit: int = 100, offset: int = 0, user: CurrentUser = Admin, db: Session = Depends(get_db)
) -> list[AuditLogOut]:
    """Nhật ký thao tác quản trị, mới nhất trước (FR-AD-07)."""
    return AdminService(db).list_audit(min(max(limit, 1), 500), max(offset, 0))


@router.put("/admin/ai-config", response_model=AIConfig)
def put_ai_config(body: AIConfig, user: CurrentUser = Admin) -> AIConfig:
    """Cấu hình nhà cung cấp LLM/STT/TTS và model dự phòng (FR-AD-05) – thẻ của Đăng."""
    if body.llm.kind != ProviderKind.LLM:
        raise AppError(422, "INVALID_PROVIDER_KIND", "llm.kind phải là LLM")
    configure_llm(body.llm.provider, body.llm.model, body.llm.fallback_provider, body.llm.fallback_model)
    return body


@router.get("/admin/users", response_model=list[UserOut])
def list_users(
    role: Role | None = None,
    q: str | None = None,
    active: bool | None = None,
    limit: int = 100,
    offset: int = 0,
    user: CurrentUser = Admin,
    db: Session = Depends(get_db),
) -> list[UserOut]:
    """Tài khoản (FR-AD-03); lọc theo vai trò, trạng thái, tìm theo tên / email / MSSV."""
    return AdminService(db).list_users(role, q, active, min(max(limit, 1), 500), max(offset, 0))


@router.post("/admin/users", response_model=CreatedUser, status_code=201)
def create_user(body: UserCreate, user: CurrentUser = Admin, db: Session = Depends(get_db)) -> CreatedUser:
    """Tạo một tài khoản. Mật khẩu ban đầu ngẫu nhiên, chỉ trả lần này. 409 USER_EXISTS khi trùng email / MSSV."""
    return AdminService(db).create_user(user, body)


@router.patch("/admin/users/{user_id}", response_model=UserOut)
def patch_user(user_id: UUID, body: UserPatch, user: CurrentUser = Admin, db: Session = Depends(get_db)) -> UserOut:
    """Đổi họ tên, khóa / mở khóa (`isActive`). Tài khoản bị khóa không đăng nhập được."""
    return AdminService(db).patch_user(user, user_id, body)


@router.post("/admin/users/{user_id}/reset-password", response_model=CreatedUser)
def reset_password(user_id: UUID, user: CurrentUser = Admin, db: Session = Depends(get_db)) -> CreatedUser:
    """Đặt lại mật khẩu ngẫu nhiên, chỉ trả lần này."""
    return AdminService(db).reset_password(user, user_id)


@router.post("/admin/users/import", response_model=ImportResult, status_code=201)
def import_students(
    file: UploadFile = File(...), user: CurrentUser = Admin, db: Session = Depends(get_db)
) -> ImportResult:
    """Nhập SV từ CSV UTF-8 (FR-AD-03), cột: mssv, ho_ten, email, [khoa]. Tạo tài khoản SV với mật khẩu ngẫu nhiên
    (trả một lần trong `created`). Dòng trùng tài khoản có sẵn vào `skipped`, dòng sai vào `errors`."""
    return AdminService(db).import_students(user, file.file.read(MAX_CSV_BYTES + 1))


@router.get("/admin/courses", response_model=list[CourseOut])
def list_courses(user: CurrentUser = Admin, db: Session = Depends(get_db)) -> list[CourseOut]:
    """Danh mục môn học (FR-AD-04)."""
    return AdminService(db).list_courses()


@router.post("/admin/courses", response_model=CourseOut, status_code=201)
def create_course(body: CourseIn, user: CurrentUser = Admin, db: Session = Depends(get_db)) -> CourseOut:
    return AdminService(db).save_course(user, body)


@router.put("/admin/courses/{course_id}", response_model=CourseOut)
def update_course(
    course_id: UUID, body: CourseIn, user: CurrentUser = Admin, db: Session = Depends(get_db)
) -> CourseOut:
    return AdminService(db).save_course(user, body, course_id)


@router.get("/admin/quotas", response_model=list[QuotaOut])
def list_quotas(
    scope: Literal["CLASS", "STUDENT"] | None = None, user: CurrentUser = Admin, db: Session = Depends(get_db)
) -> list[QuotaOut]:
    """Hạn mức đã đặt kèm mức đã dùng (FR-AD-06)."""
    return QuotaService(db).list(scope)


@router.put("/admin/quotas", response_model=QuotaOut)
def put_quotas(body: QuotaIn, user: CurrentUser = Admin, db: Session = Depends(get_db)) -> QuotaOut:
    """Đặt hạn mức token / phút ghi âm cho một lớp hoặc một SV (FR-AD-06); `null` = không giới hạn, cả hai `null` = bỏ.
    Vượt hạn mức thì bắt đầu phiên, gửi lượt, tải ghi âm trả 429 QUOTA_EXCEEDED."""
    svc = AdminService(db)
    out = QuotaService(db).set(body)
    svc.audit(user, "QUOTA_SET", "usage_quota", body.scope_id, body.model_dump(mode="json"))
    db.commit()
    return out


@router.get("/notifications")
def my_notifications(user: CurrentUser = AnyUser) -> list[dict]:
    """Thông báo trong ứng dụng (FR-AD-08); realtime qua kênh user:{id}."""
    raise NotImplementedYet("C2-19")
