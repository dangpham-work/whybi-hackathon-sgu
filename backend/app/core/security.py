"""Băm mật khẩu (Argon2id) và JWT – NFR-07, mục 5.6.1. Chủ: Long (C2-07).

Ba loại token, cùng ký HS256 bằng JWT_SECRET, phân biệt bằng claim `typ`:
- `access`: 30 phút (JWT_ACCESS_MINUTES) – gửi ở header Authorization: Bearer.
- `refresh`: 7 ngày (JWT_REFRESH_DAYS) – chỉ dùng ở POST /auth/refresh; mỗi lần làm mới thì thu hồi cái cũ;
  kèm dấu vân tay mật khẩu nên đổi mật khẩu là các phiên cũ không làm mới được nữa.
- `reset`: 30 phút – liên kết đặt lại mật khẩu; kèm dấu vân tay của mật khẩu hiện tại nên dùng được đúng một lần.
Mọi token có `jti` để thu hồi khi đăng xuất (services/auth.py).
"""

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID, uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings
from app.core.errors import AppError
from app.models.enums import Role

TokenType = Literal["access", "refresh", "reset"]
ALGORITHM = "HS256"
RESET_MINUTES = 30

_hasher = PasswordHasher()  # Argon2id, tham số mặc định của argon2-cffi (RFC 9106 low-memory)
_DUMMY_HASH = _hasher.hash("whybi-dummy-password")


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, plain)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def burn_verify_time(plain: str) -> None:
    """Chạy verify trên hash giả khi email không tồn tại – thời gian trả lời như khi có tài khoản."""
    verify_password(plain, _DUMMY_HASH)


def password_fingerprint(password_hash: str) -> str:
    """Đổi mật khẩu ⇒ dấu vân tay đổi ⇒ token đặt lại cũ hết hiệu lực."""
    return hashlib.sha256(password_hash.encode()).hexdigest()[:16]


_DEFAULT_SECRET = "change-me-to-a-long-random-string"


def _secret() -> str:
    """Ngoài dev / test bắt buộc JWT_SECRET riêng, dài ≥ 32 ký tự – không chạy demo / prod bằng khóa mẫu."""
    s = get_settings()
    if s.app_env not in ("dev", "test") and (s.jwt_secret == _DEFAULT_SECRET or len(s.jwt_secret) < 32):
        raise RuntimeError("JWT_SECRET chưa đặt (hoặc quá ngắn) cho môi trường " + s.app_env)
    return s.jwt_secret


def _encode(sub: UUID, typ: TokenType, ttl: timedelta, now: datetime | None, **extra: Any) -> str:
    now = now or datetime.now(UTC)
    iat = int(now.timestamp())
    claims = {"sub": str(sub), "typ": typ, "jti": uuid4().hex, "iat": iat, "exp": iat + int(ttl.total_seconds())}
    claims.update(extra)
    return jwt.encode(claims, _secret(), algorithm=ALGORITHM)


def create_access_token(user_id: UUID, role: Role, full_name: str = "", now: datetime | None = None) -> str:
    minutes = get_settings().jwt_access_minutes
    return _encode(user_id, "access", timedelta(minutes=minutes), now, role=str(role), name=full_name)


def create_refresh_token(user_id: UUID, password_hash: str, now: datetime | None = None) -> str:
    """Kèm dấu vân tay mật khẩu: đổi / đặt lại mật khẩu ⇒ mọi refresh token cũ hết dùng được."""
    ttl = timedelta(days=get_settings().jwt_refresh_days)
    return _encode(user_id, "refresh", ttl, now, pwf=password_fingerprint(password_hash))


def create_reset_token(user_id: UUID, password_hash: str, now: datetime | None = None) -> str:
    return _encode(user_id, "reset", timedelta(minutes=RESET_MINUTES), now, pwf=password_fingerprint(password_hash))


def decode_token(token: str, expected: TokenType, now: datetime | None = None) -> dict[str, Any]:
    """Giải mã và kiểm chữ ký, hạn, loại. Lỗi ⇒ AppError 401 TOKEN_EXPIRED / INVALID_TOKEN."""
    try:
        claims = jwt.decode(
            token,
            _secret(),
            algorithms=[ALGORITHM],
            options={"require": ["sub", "typ", "jti", "iat", "exp"], "verify_exp": False},
        )
    except jwt.PyJWTError:
        raise AppError(401, "INVALID_TOKEN", "Token không hợp lệ") from None
    # Tự kiểm hạn để test truyền được `now` (PyJWT luôn dùng giờ hệ thống)
    current = int((now or datetime.now(UTC)).timestamp())
    if current >= int(claims["exp"]):
        raise AppError(401, "TOKEN_EXPIRED", "Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại")
    if claims["typ"] != expected:
        raise AppError(401, "INVALID_TOKEN", "Sai loại token")
    return claims
