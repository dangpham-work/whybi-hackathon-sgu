"""Băm mật khẩu (Argon2id) và JWT 30 phút + refresh token – NFR-07, mục 5.6.1. Chủ: Long (C2-07)."""

from uuid import UUID

from app.models.enums import Role


def hash_password(plain: str) -> str:
    """TODO(C2-07): argon2.PasswordHasher().hash(plain)"""
    raise NotImplementedError("C2-07")


def verify_password(plain: str, hashed: str) -> bool:
    raise NotImplementedError("C2-07")


def create_access_token(user_id: UUID, role: Role) -> str:
    """TODO(C2-07): jwt.encode({sub, role, exp = now + JWT_ACCESS_MINUTES}, JWT_SECRET, HS256)"""
    raise NotImplementedError("C2-07")


def decode_access_token(token: str) -> dict:
    raise NotImplementedError("C2-07")
