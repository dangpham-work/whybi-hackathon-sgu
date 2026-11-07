"""Quản trị – FR-AD-03…08. Chủ: Long (C2-18, C2-19), Đăng (C1-02: ai-config)."""

from uuid import UUID

from fastapi import APIRouter, File, UploadFile

from app.api.deps import Admin, AnyUser, CurrentUser, LecturerOrAdmin
from app.core.errors import NotImplementedYet
from app.models.enums import ProviderKind
from app.models.schemas.common import ApiModel

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


@router.get("/admin/flags")
def list_flags(resolved: bool = False, user: CurrentUser = LecturerOrAdmin) -> list[dict]:
    """Danh sách cờ vi phạm (FR-AD-07)."""
    raise NotImplementedYet("C2-18")


@router.post("/admin/flags/{flag_id}/resolve")
def resolve_flag(flag_id: UUID, user: CurrentUser = LecturerOrAdmin) -> dict:
    raise NotImplementedYet("C2-18")


@router.put("/admin/ai-config", response_model=AIConfig)
def put_ai_config(body: AIConfig, user: CurrentUser = Admin) -> AIConfig:
    """Cấu hình nhà cung cấp LLM/STT/TTS và model dự phòng (FR-AD-05) – thẻ của Đăng."""
    raise NotImplementedYet("C1-02")


@router.get("/admin/users")
def list_users(user: CurrentUser = Admin) -> list[dict]:
    raise NotImplementedYet("C2-18")


@router.post("/admin/users/import", status_code=201)
def import_students(file: UploadFile = File(...), user: CurrentUser = Admin) -> dict:
    """Nhập danh sách SV từ CSV (FR-AD-03)."""
    raise NotImplementedYet("C2-18")


@router.get("/admin/courses")
def list_courses(user: CurrentUser = Admin) -> list[dict]:
    """Danh mục môn học (FR-AD-04)."""
    raise NotImplementedYet("C2-18")


@router.put("/admin/quotas")
def put_quotas(user: CurrentUser = Admin) -> dict:
    """Hạn mức token / phút ghi âm theo lớp, theo SV (FR-AD-06)."""
    raise NotImplementedYet("C2-18")


@router.get("/notifications")
def my_notifications(user: CurrentUser = AnyUser) -> list[dict]:
    """Thông báo trong ứng dụng (FR-AD-08); realtime qua kênh user:{id}."""
    raise NotImplementedYet("C2-19")
