"""AuthService – đăng nhập, làm mới, đăng xuất, quên / đặt lại mật khẩu, hồ sơ (FR-AD-01, NFR-07). Chủ: Long (C2-07).

- Người dùng đọc qua `UserStore` (bản SQL ở đây; bản trong bộ nhớ cho test).
- Đăng xuất / làm mới thu hồi token theo `jti` trong `Revocations` (Redis, khóa tự hết hạn cùng token).
- Thư đặt lại mật khẩu gửi qua `Mailer`. Chưa có SMTP thì chỉ ghi log ở dev; ở prod không ghi token ra log.
"""

import logging
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import (
    burn_verify_time,
    create_access_token,
    create_refresh_token,
    create_reset_token,
    decode_token,
    hash_password,
    password_fingerprint,
    verify_password,
)
from app.models.enums import Role
from app.models.users import Student, User

log = logging.getLogger(__name__)

Mailer = Callable[[str, str], None]  # (email, reset_token)


@dataclass
class UserRecord:
    id: UUID
    email: str
    full_name: str
    role: Role
    password_hash: str
    is_active: bool = True
    avatar_url: str | None = None


class UserStore(Protocol):
    def by_email(self, email: str) -> UserRecord | None: ...
    def by_id(self, user_id: UUID) -> UserRecord | None: ...
    def update(self, user_id: UUID, **fields: Any) -> UserRecord: ...


class InMemoryUserStore:
    def __init__(self, users: Iterable[UserRecord] = ()) -> None:
        self._by_id = {u.id: u for u in users}

    def by_email(self, email: str) -> UserRecord | None:
        return next((u for u in self._by_id.values() if u.email.lower() == email.lower()), None)

    def by_id(self, user_id: UUID) -> UserRecord | None:
        return self._by_id.get(user_id)

    def update(self, user_id: UUID, **fields: Any) -> UserRecord:
        u = replace(self._by_id[user_id], **fields)
        self._by_id[user_id] = u
        return u


class SqlUserStore:
    """Đọc / ghi bảng `users`. Đăng ký tài khoản và nhập CSV là việc của C2-18."""

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _record(u: User) -> UserRecord:
        return UserRecord(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            role=Role(u.role),
            password_hash=u.password_hash,
            is_active=u.is_active,
            avatar_url=u.avatar_url,
        )

    def by_email(self, email: str) -> UserRecord | None:
        u = self.db.scalar(select(User).where(func.lower(User.email) == email.lower()))
        return self._record(u) if u else None

    def by_id(self, user_id: UUID) -> UserRecord | None:
        u = self.db.get(User, user_id)
        return self._record(u) if u else None

    def update(self, user_id: UUID, **fields: Any) -> UserRecord:
        u = self.db.get(User, user_id)
        for k, v in fields.items():
            setattr(u, k, v)
        self.db.commit()
        return self._record(u)


class Revocations(Protocol):
    def revoke(self, jti: str, exp: int) -> None: ...

    def revoke_once(self, jti: str, exp: int) -> bool:
        """Thu hồi nguyên tử; False nếu đã bị thu hồi trước đó (hai request dùng cùng một token)."""
        ...

    def is_revoked(self, jti: str) -> bool: ...


class InMemoryRevocations:
    def __init__(self) -> None:
        self._jti: dict[str, int] = {}
        self._lock = threading.Lock()

    def revoke(self, jti: str, exp: int) -> None:
        self._jti[jti] = exp

    def revoke_once(self, jti: str, exp: int) -> bool:
        with self._lock:
            if jti in self._jti:
                return False
            self._jti[jti] = exp
            return True

    def is_revoked(self, jti: str) -> bool:
        return jti in self._jti


class RedisRevocations:
    PREFIX = "auth:revoked:"

    def __init__(self, redis_url: str) -> None:
        import redis

        self._r = redis.Redis.from_url(redis_url)

    @staticmethod
    def _ttl(exp: int) -> int:
        return max(1, exp - int(datetime.now(UTC).timestamp()))

    def revoke(self, jti: str, exp: int) -> None:
        self._r.set(self.PREFIX + jti, 1, ex=self._ttl(exp))

    def revoke_once(self, jti: str, exp: int) -> bool:
        return bool(self._r.set(self.PREFIX + jti, 1, ex=self._ttl(exp), nx=True))

    def is_revoked(self, jti: str) -> bool:
        return bool(self._r.exists(self.PREFIX + jti))


def _mask(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"


def log_mailer(email: str, token: str) -> None:
    """Tạm tới khi có SMTP / NotificationService: dev (DEMO_MODE tắt) in token để thử; nơi khác chỉ ghi đã gửi."""
    s = get_settings()
    if s.app_env in ("dev", "test") and not s.demo_mode:
        log.warning("[dev] token đặt lại mật khẩu cho %s: %s", email, token)
    else:
        log.info("đã tạo yêu cầu đặt lại mật khẩu cho %s", _mask(email))


@dataclass
class Tokens:
    access_token: str
    refresh_token: str
    expires_in: int


def verified_claims(token: str, typ: str, revocations: Revocations) -> dict[str, Any]:
    """Giải mã + kiểm token chưa bị thu hồi. Dùng cho mọi request (deps.get_current_user) – không chạm CSDL."""
    claims = decode_token(token, typ)  # type: ignore[arg-type]
    if revocations.is_revoked(claims["jti"]):
        raise AppError(401, "TOKEN_REVOKED", "Token đã bị thu hồi, vui lòng đăng nhập lại")
    return claims


_BAD_LOGIN = AppError(401, "INVALID_CREDENTIALS", "Email hoặc mật khẩu không đúng")


class AuthService:
    def __init__(self, users: UserStore, revocations: Revocations, mailer: Mailer = log_mailer) -> None:
        self.users = users
        self.revocations = revocations
        self.mailer = mailer

    def _issue(self, u: UserRecord) -> Tokens:
        return Tokens(
            access_token=create_access_token(u.id, u.role, u.full_name),
            refresh_token=create_refresh_token(u.id, u.password_hash),
            expires_in=get_settings().jwt_access_minutes * 60,
        )

    def login(self, email: str, password: str) -> Tokens:
        u = self.users.by_email(email)
        if u is None:
            burn_verify_time(password)  # không lộ email có tồn tại qua thời gian trả lời
            raise _BAD_LOGIN
        if not verify_password(password, u.password_hash):
            raise _BAD_LOGIN
        if not u.is_active:
            raise AppError(403, "ACCOUNT_DISABLED", "Tài khoản đã bị khóa")
        return self._issue(u)

    def _claims(self, token: str, typ: str) -> dict[str, Any]:
        return verified_claims(token, typ, self.revocations)

    def refresh(self, refresh_token: str) -> Tokens:
        claims = self._claims(refresh_token, "refresh")
        u = self.users.by_id(UUID(claims["sub"]))
        if u is None or not u.is_active:
            raise AppError(401, "INVALID_TOKEN", "Tài khoản không còn hiệu lực")
        if claims.get("pwf") != password_fingerprint(u.password_hash):
            raise AppError(401, "TOKEN_REVOKED", "Mật khẩu đã đổi, vui lòng đăng nhập lại")
        # Xoay vòng, nguyên tử: hai request cùng một refresh token thì chỉ một cái được cặp mới
        if not self.revocations.revoke_once(claims["jti"], claims["exp"]):
            raise AppError(401, "TOKEN_REVOKED", "Token đã bị thu hồi, vui lòng đăng nhập lại")
        return self._issue(u)

    def logout(self, access_claims: dict[str, Any], refresh_token: str | None = None) -> None:
        self.revocations.revoke(access_claims["jti"], access_claims["exp"])
        if refresh_token:
            try:
                claims = decode_token(refresh_token, "refresh")
            except AppError:
                return
            if claims["sub"] == access_claims["sub"]:
                self.revocations.revoke(claims["jti"], claims["exp"])

    def forgot_password(self, email: str) -> None:
        """Luôn trả như nhau dù email có hay không (không lộ tài khoản)."""
        u = self.users.by_email(email)
        if u is None or not u.is_active:
            return
        self.mailer(u.email, create_reset_token(u.id, u.password_hash))

    def reset_password(self, token: str, new_password: str) -> None:
        claims = self._claims(token, "reset")
        u = self.users.by_id(UUID(claims["sub"]))
        if u is None or claims.get("pwf") != password_fingerprint(u.password_hash):
            raise AppError(401, "INVALID_TOKEN", "Liên kết đặt lại mật khẩu đã dùng hoặc không hợp lệ")
        # Consume before writing: concurrent requests may both read the old password.
        if not self.revocations.revoke_once(claims["jti"], claims["exp"]):
            raise AppError(401, "TOKEN_REVOKED", "Liên kết đặt lại mật khẩu đã dùng")
        self.users.update(u.id, password_hash=hash_password(new_password))

    def me(self, user_id: UUID) -> UserRecord:
        u = self.users.by_id(user_id)
        if u is None:
            raise AppError(404, "USER_NOT_FOUND", "Không tìm thấy người dùng")
        return u

    def update_profile(
        self,
        user_id: UUID,
        *,
        full_name: str | None = None,
        avatar_url: str | None = None,
        current_password: str | None = None,
        new_password: str | None = None,
    ) -> UserRecord:
        u = self.me(user_id)
        fields: dict[str, Any] = {}
        if full_name is not None:
            fields["full_name"] = full_name
        if avatar_url is not None:
            fields["avatar_url"] = avatar_url
        if new_password is not None:
            if not current_password:
                raise AppError(400, "CURRENT_PASSWORD_REQUIRED", "Cần nhập mật khẩu hiện tại để đổi mật khẩu")
            if not verify_password(current_password, u.password_hash):
                raise AppError(400, "WRONG_PASSWORD", "Mật khẩu hiện tại không đúng")
            fields["password_hash"] = hash_password(new_password)
        return self.users.update(user_id, **fields) if fields else u


def student_identities(db: Session, ids: Iterable[UUID]) -> dict[UUID, tuple[str, str]]:
    """id → (họ tên, MSSV) theo lô – cho bản đồ nhiệt (C2-13) đọc tên SV qua service người dùng. Chỉ đọc."""
    ids = list(ids)
    if not ids:
        return {}
    q = (
        select(User.id, User.full_name, Student.student_code)
        .join(Student, Student.user_id == User.id, isouter=True)
        .where(User.id.in_(ids))
    )
    return {uid: (name, code or "") for uid, name, code in db.execute(q)}
