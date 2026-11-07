"""Phụ thuộc dùng chung cho router: người dùng hiện tại, kiểm tra vai trò (RBAC – FR-AD-02, NFR-08).

TODO(C2-07): giải mã JWT thật (app/core/security.py), nạp User từ CSDL, kiểm quyền theo lớp.
"""

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID, uuid5

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.core.errors import AppError
from app.models.enums import Role

bearer = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    id: UUID
    role: Role
    full_name: str = ""


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> CurrentUser:
    if creds is None:
        raise AppError(401, "UNAUTHORIZED", "Thiếu token đăng nhập")
    dev_user = _dev_user(creds.credentials)
    if dev_user is not None:
        return dev_user
    # TODO(C2-07): from app.core.security import decode_access_token
    raise AppError(501, "NOT_IMPLEMENTED", "Xác thực chưa cài đặt – xem thẻ C2-07", {"card": "C2-07"})


# TẠM THỜI tới C2-07: token cố định để Đăng / Thắng / Quyền gọi API khi chưa có đăng nhập thật.
# Chỉ nhận khi ALLOW_DEV_TOKENS=true, APP_ENV là dev hoặc test và DEMO_MODE tắt; demo / prod luôn từ chối.
# C2-07 xóa khối này.
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
