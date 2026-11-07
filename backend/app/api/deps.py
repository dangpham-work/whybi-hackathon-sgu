"""Phụ thuộc dùng chung cho router: người dùng hiện tại, kiểm tra vai trò (RBAC – FR-AD-02, NFR-08). Chủ: Long.

- `get_current_user`: giải mã JWT access (30 phút), kiểm token chưa bị thu hồi. Không truy vấn CSDL mỗi request:
  vai trò lấy từ token. Khóa tài khoản có hiệu lực chậm nhất sau 30 phút (khi token hết hạn).
- Kiểm quyền theo lớp (GV chỉ lớp mình, SV chỉ lớp đã tham gia – Bảng 5.13) làm ở service của từng thẻ (C2-08…).
"""

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from uuid import UUID, uuid5

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import get_db
from app.models.enums import Role
from app.services.auth import (
    AuthService,
    InMemoryRevocations,
    Mailer,
    RedisRevocations,
    Revocations,
    SqlUserStore,
    UserStore,
    log_mailer,
    verified_claims,
)

bearer = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    id: UUID
    role: Role
    full_name: str = ""
    jti: str = ""
    exp: int = 0


def get_user_store(db: Session = Depends(get_db)) -> UserStore:
    return SqlUserStore(db)


@lru_cache
def _revocations() -> Revocations:
    s = get_settings()
    return InMemoryRevocations() if s.app_env == "test" else RedisRevocations(s.redis_url)


def get_revocations() -> Revocations:
    return _revocations()


def get_mailer() -> Mailer:
    return log_mailer


def get_auth_service(
    users: UserStore = Depends(get_user_store),
    revocations: Revocations = Depends(get_revocations),
    mailer: Mailer = Depends(get_mailer),
) -> AuthService:
    return AuthService(users, revocations, mailer)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    revocations: Revocations = Depends(get_revocations),
) -> CurrentUser:
    if creds is None:
        raise AppError(401, "UNAUTHORIZED", "Thiếu token đăng nhập")
    dev_user = _dev_user(creds.credentials)
    if dev_user is not None:
        return dev_user
    claims = verified_claims(creds.credentials, "access", revocations)
    try:
        role = Role(claims["role"])
        user_id = UUID(claims["sub"])
    except (KeyError, ValueError):
        raise AppError(401, "INVALID_TOKEN", "Token không hợp lệ") from None
    return CurrentUser(id=user_id, role=role, full_name=claims.get("name", ""), jti=claims["jti"], exp=claims["exp"])


# TẠM THỜI tới khi seed tài khoản vào CSDL (KT-02 – scripts/seed_db.py): token cố định để Đăng / Thắng / Quyền
# gọi API khi CSDL chưa có tài khoản. Chỉ nhận khi ALLOW_DEV_TOKENS=true, APP_ENV là dev hoặc test và DEMO_MODE
# tắt; demo / prod luôn từ chối. Xóa khối này khi seed tài khoản đã merge.
_DEV_TOKENS = {
    "dev-lecturer": (Role.LECTURER, "GV dev"),
    "dev-student": (Role.STUDENT, "SV dev"),
    "dev-admin": (Role.ADMIN, "QTV dev"),
}
_DEV_NS = UUID("8f1d6a52-5a0e-4e0b-9a59-2c1b7f3e0c11")


def _dev_user(token: str) -> CurrentUser | None:
    s = get_settings()
    if not s.allow_dev_tokens or s.demo_mode or s.app_env not in ("dev", "test") or token not in _DEV_TOKENS:
        return None
    role, name = _DEV_TOKENS[token]
    return CurrentUser(id=uuid5(_DEV_NS, token), role=role, full_name=name)


def require_role(*roles: Role) -> Callable[[CurrentUser], CurrentUser]:
    def checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in roles:
            raise AppError(403, "FORBIDDEN", "Vai trò không được phép")
        return user

    return checker


Lecturer = Depends(require_role(Role.LECTURER))
Student = Depends(require_role(Role.STUDENT))
Admin = Depends(require_role(Role.ADMIN))
AnyUser = Depends(get_current_user)
LecturerOrStudent = Depends(require_role(Role.LECTURER, Role.STUDENT))
LecturerOrAdmin = Depends(require_role(Role.LECTURER, Role.ADMIN))
