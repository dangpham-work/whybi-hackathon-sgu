"""Xác thực – FR-AD-01. Chủ: Long (C2-07)."""

from fastapi import APIRouter
from pydantic import EmailStr

from app.api.deps import AnyUser, CurrentUser
from app.core.errors import NotImplementedYet
from app.models.enums import Role
from app.models.schemas.common import ApiModel

router = APIRouter(tags=["auth"])


class LoginRequest(ApiModel):
    email: EmailStr
    password: str


class TokenPair(ApiModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 1800  # JWT 30 phút – NFR-07


class Me(ApiModel):
    id: str
    full_name: str
    email: EmailStr
    role: Role
    avatar_url: str | None = None


@router.post("/auth/login", response_model=TokenPair)
def login(body: LoginRequest) -> TokenPair:
    raise NotImplementedYet("C2-07")


@router.post("/auth/refresh", response_model=TokenPair)
def refresh() -> TokenPair:
    raise NotImplementedYet("C2-07")


@router.post("/auth/logout", status_code=204)
def logout(user: CurrentUser = AnyUser) -> None:
    raise NotImplementedYet("C2-07")


@router.post("/auth/forgot-password", status_code=202)
def forgot_password(email: EmailStr) -> None:
    raise NotImplementedYet("C2-07")


@router.get("/me", response_model=Me)
def me(user: CurrentUser = AnyUser) -> Me:
    raise NotImplementedYet("C2-07")


@router.patch("/me", response_model=Me)
def update_me(user: CurrentUser = AnyUser) -> Me:
    raise NotImplementedYet("C2-07")
