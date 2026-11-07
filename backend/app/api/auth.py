"""Xác thực – FR-AD-01, NFR-07. Chủ: Long (C2-07).

Email kiểm bằng email-validator với `test_environment=True`: chấp nhận đuôi `.test` của tài khoản mẫu
(`gv@whybi.test`, seed/users.json) mà `EmailStr` từ chối. Không tra DNS. Luôn chuẩn hóa về chữ thường.
"""

from typing import Annotated

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Depends
from pydantic import AfterValidator, Field, HttpUrl

from app.api.deps import AnyUser, CurrentUser, get_auth_service
from app.models.enums import Role
from app.models.schemas.common import ApiModel
from app.services.auth import AuthService, Tokens, UserRecord

router = APIRouter(tags=["auth"])


def _email(value: str) -> str:
    try:
        return validate_email(value.strip(), check_deliverability=False, test_environment=True).normalized.lower()
    except EmailNotValidError as exc:
        raise ValueError(f"email không hợp lệ: {exc}") from None


Email = Annotated[str, AfterValidator(_email)]
Password = Annotated[str, Field(min_length=8, max_length=128)]


class LoginRequest(ApiModel):
    email: Email
    password: str = Field(min_length=1, max_length=128)


class TokenPair(ApiModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 1800  # JWT 30 phút – NFR-07

    @classmethod
    def of(cls, t: Tokens) -> "TokenPair":
        return cls(access_token=t.access_token, refresh_token=t.refresh_token, expires_in=t.expires_in)


class RefreshRequest(ApiModel):
    refresh_token: str


class LogoutRequest(ApiModel):
    refresh_token: str | None = None


class ForgotPasswordRequest(ApiModel):
    email: Email


class ResetPasswordRequest(ApiModel):
    token: str
    new_password: Password


class Me(ApiModel):
    id: str
    full_name: str
    email: str
    role: Role
    avatar_url: str | None = None

    @classmethod
    def of(cls, u: UserRecord) -> "Me":
        return cls(id=str(u.id), full_name=u.full_name, email=u.email, role=u.role, avatar_url=u.avatar_url)


class UpdateMe(ApiModel):
    full_name: str | None = Field(None, min_length=1, max_length=120)
    avatar_url: HttpUrl | None = None
    current_password: str | None = None
    new_password: Password | None = None


Auth = Annotated[AuthService, Depends(get_auth_service)]


@router.post("/auth/login", response_model=TokenPair)
def login(body: LoginRequest, auth: Auth) -> TokenPair:
    return TokenPair.of(auth.login(body.email, body.password))


@router.post("/auth/refresh", response_model=TokenPair)
def refresh(body: RefreshRequest, auth: Auth) -> TokenPair:
    """Đổi refresh token lấy cặp token mới; refresh cũ bị thu hồi."""
    return TokenPair.of(auth.refresh(body.refresh_token))


@router.post("/auth/logout", status_code=204)
def logout(auth: Auth, body: LogoutRequest | None = None, user: CurrentUser = AnyUser) -> None:
    """Thu hồi access token hiện tại (và refresh token nếu gửi kèm)."""
    auth.logout({"sub": str(user.id), "jti": user.jti, "exp": user.exp}, body.refresh_token if body else None)


@router.post("/auth/forgot-password", status_code=202)
def forgot_password(body: ForgotPasswordRequest, auth: Auth) -> None:
    """Luôn 202 – không cho biết email có tồn tại hay không."""
    auth.forgot_password(body.email)


@router.post("/auth/reset-password", status_code=204)
def reset_password(body: ResetPasswordRequest, auth: Auth) -> None:
    auth.reset_password(body.token, body.new_password)


@router.get("/me", response_model=Me)
def me(auth: Auth, user: CurrentUser = AnyUser) -> Me:
    return Me.of(auth.me(user.id))


@router.patch("/me", response_model=Me)
def update_me(body: UpdateMe, auth: Auth, user: CurrentUser = AnyUser) -> Me:
    return Me.of(
        auth.update_profile(
            user.id,
            full_name=body.full_name,
            avatar_url=str(body.avatar_url) if body.avatar_url else None,
            current_password=body.current_password,
            new_password=body.new_password,
        )
    )
