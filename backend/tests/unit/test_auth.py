"""C2-07 – Xong khi: tài khoản SV gọi API của GV bị 403; token hết hạn sau 30 phút.

Kho người dùng và danh sách token thu hồi dùng bản trong bộ nhớ (ghi đè dependency) – không cần Postgres / Redis.
Bản SQL được kiểm ở test_auth_db.py khi có TEST_DATABASE_URL.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.api import deps
from app.core.security import create_access_token, decode_token, hash_password, verify_password
from app.main import app
from app.models.enums import Role
from app.services.auth import InMemoryRevocations, InMemoryUserStore, UserRecord

PASSWORD = "Whybi@2026"
PASSWORD_HASH = hash_password(PASSWORD)  # băm một lần – Argon2 cố ý chậm


def _user(email: str, role: Role, name: str) -> UserRecord:
    return UserRecord(id=uuid4(), email=email, full_name=name, role=role, password_hash=PASSWORD_HASH, is_active=True)


@pytest.fixture
def store() -> InMemoryUserStore:
    return InMemoryUserStore(
        [
            _user("gv@whybi.test", Role.LECTURER, "TS. Nguyễn Văn Bình"),
            _user("sv01@whybi.test", Role.STUDENT, "Nguyễn Văn An"),
            _user("admin@whybi.test", Role.ADMIN, "Quản trị Whybi"),
        ]
    )


@pytest.fixture
def mailbox() -> list[tuple[str, str]]:
    return []


@pytest.fixture
def api(store, mailbox):
    revocations = InMemoryRevocations()
    app.dependency_overrides[deps.get_user_store] = lambda: store
    app.dependency_overrides[deps.get_revocations] = lambda: revocations
    app.dependency_overrides[deps.get_mailer] = lambda: lambda email, token: mailbox.append((email, token))
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def login(api, email="gv@whybi.test", password=PASSWORD):
    return api.post("/api/v1/auth/login", json={"email": email, "password": password})


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- Băm mật khẩu, JWT -------------------------------------------------------------------------


def test_password_hash_is_argon2id():
    h = hash_password(PASSWORD)
    assert h.startswith("$argon2id$")
    assert verify_password(PASSWORD, h)
    assert not verify_password("sai-mat-khau", h)
    assert not verify_password(PASSWORD, "khong-phai-hash")


def test_access_token_expires_after_30_minutes():
    now = datetime.now(UTC)
    token = create_access_token(uuid4(), Role.STUDENT, now=now)
    claims = decode_token(token, "access", now=now + timedelta(minutes=29, seconds=59))
    assert claims["exp"] - claims["iat"] == 30 * 60
    with pytest.raises(Exception) as exc:
        decode_token(token, "access", now=now + timedelta(minutes=30, seconds=1))
    assert getattr(exc.value, "code", None) == "TOKEN_EXPIRED"


def test_refresh_token_not_accepted_as_access(api):
    tokens = login(api).json()
    r = api.get("/api/v1/me", headers=bearer(tokens["refreshToken"]))
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "INVALID_TOKEN"


def test_tampered_token_rejected(api):
    token = login(api).json()["accessToken"]
    r = api.get("/api/v1/me", headers=bearer(token[:-2] + ("AA" if not token.endswith("AA") else "BB")))
    assert r.status_code == 401


# --- Đăng nhập (email .test của tài khoản mẫu phải hợp lệ) --------------------------------------


def test_login_demo_account_with_test_domain(api):
    r = login(api)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tokenType"] == "bearer" and body["expiresIn"] == 1800
    assert decode_token(body["accessToken"], "access")["role"] == "LECTURER"


def test_login_email_case_insensitive(api):
    assert login(api, email="  GV@Whybi.Test ").status_code == 200


def test_login_wrong_password_and_unknown_email_same_error(api):
    a, b = login(api, password="sai"), login(api, email="ai@whybi.test")
    assert a.status_code == b.status_code == 401
    assert a.json()["error"] == b.json()["error"]
    assert a.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_login_invalid_email_still_422(api):
    r = api.post("/api/v1/auth/login", json={"email": "khong-phai-email", "password": "x"})
    assert r.status_code == 422


def test_login_disabled_account(api, store):
    store.by_email("sv01@whybi.test").is_active = False
    r = login(api, email="sv01@whybi.test")
    assert r.status_code == 403 and r.json()["error"]["code"] == "ACCOUNT_DISABLED"


# --- GET / PATCH /me ---------------------------------------------------------------------------


def test_me(api):
    token = login(api).json()["accessToken"]
    r = api.get("/api/v1/me", headers=bearer(token))
    assert r.status_code == 200
    assert r.json() | {"id": None} == {
        "id": None,
        "fullName": "TS. Nguyễn Văn Bình",
        "email": "gv@whybi.test",
        "role": "LECTURER",
        "avatarUrl": None,
    }


def test_update_profile_and_change_password(api):
    token = login(api, email="sv01@whybi.test").json()["accessToken"]
    r = api.patch("/api/v1/me", headers=bearer(token), json={"fullName": "Nguyễn An", "avatarUrl": "https://x/a.png"})
    assert r.status_code == 200 and r.json()["fullName"] == "Nguyễn An"

    r = api.patch("/api/v1/me", headers=bearer(token), json={"newPassword": "MatKhauMoi1"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "CURRENT_PASSWORD_REQUIRED"
    r = api.patch("/api/v1/me", headers=bearer(token), json={"currentPassword": "sai", "newPassword": "MatKhauMoi1"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "WRONG_PASSWORD"
    r = api.patch("/api/v1/me", headers=bearer(token), json={"currentPassword": PASSWORD, "newPassword": "MatKhauMoi1"})
    assert r.status_code == 200
    assert login(api, email="sv01@whybi.test").status_code == 401
    assert login(api, email="sv01@whybi.test", password="MatKhauMoi1").status_code == 200


def test_new_password_too_short(api):
    token = login(api).json()["accessToken"]
    r = api.patch("/api/v1/me", headers=bearer(token), json={"currentPassword": PASSWORD, "newPassword": "ngan"})
    assert r.status_code == 422


# --- Làm mới, đăng xuất ------------------------------------------------------------------------


def test_refresh_rotates_and_old_refresh_is_revoked(api):
    tokens = login(api).json()
    r = api.post("/api/v1/auth/refresh", json={"refreshToken": tokens["refreshToken"]})
    assert r.status_code == 200
    new = r.json()
    assert api.get("/api/v1/me", headers=bearer(new["accessToken"])).status_code == 200
    again = api.post("/api/v1/auth/refresh", json={"refreshToken": tokens["refreshToken"]})
    assert again.status_code == 401 and again.json()["error"]["code"] == "TOKEN_REVOKED"


def test_logout_revokes_access_and_refresh(api):
    tokens = login(api).json()
    r = api.post(
        "/api/v1/auth/logout", headers=bearer(tokens["accessToken"]), json={"refreshToken": tokens["refreshToken"]}
    )
    assert r.status_code == 204
    me = api.get("/api/v1/me", headers=bearer(tokens["accessToken"]))
    assert me.status_code == 401 and me.json()["error"]["code"] == "TOKEN_REVOKED"
    assert api.post("/api/v1/auth/refresh", json={"refreshToken": tokens["refreshToken"]}).status_code == 401


# --- Quên mật khẩu -----------------------------------------------------------------------------


def test_forgot_password_does_not_reveal_accounts(api, mailbox):
    assert api.post("/api/v1/auth/forgot-password", json={"email": "ai@whybi.test"}).status_code == 202
    assert mailbox == []
    assert api.post("/api/v1/auth/forgot-password", json={"email": "sv01@whybi.test"}).status_code == 202
    assert [m[0] for m in mailbox] == ["sv01@whybi.test"]


def test_reset_password_once(api, mailbox):
    api.post("/api/v1/auth/forgot-password", json={"email": "sv01@whybi.test"})
    token = mailbox[0][1]
    r = api.post("/api/v1/auth/reset-password", json={"token": token, "newPassword": "DatLai2026"})
    assert r.status_code == 204
    assert login(api, email="sv01@whybi.test", password="DatLai2026").status_code == 200
    # Dùng lại token đặt lại → bị từ chối (đã đổi mật khẩu)
    again = api.post("/api/v1/auth/reset-password", json={"token": token, "newPassword": "LanNua2026"})
    assert again.status_code == 401


def test_concurrent_reset_consumes_token_once(monkeypatch, store):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from app.core.errors import AppError
    from app.core.security import create_reset_token
    from app.services.auth import AuthService

    user = store.by_email("sv01@whybi.test")
    token = create_reset_token(user.id, user.password_hash)
    barrier = Barrier(2)
    original_by_id = store.by_id
    writes = []
    original_update = store.update

    def simultaneous_read(user_id):
        record = original_by_id(user_id)
        barrier.wait(timeout=5)
        return record

    def record_update(user_id, **fields):
        writes.append(fields)
        return original_update(user_id, **fields)

    monkeypatch.setattr(store, "by_id", simultaneous_read)
    monkeypatch.setattr(store, "update", record_update)
    service = AuthService(store, InMemoryRevocations())

    def reset(password):
        try:
            service.reset_password(token, password)
            return "ok"
        except AppError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reset, ["FirstPass2026", "SecondPass2026"]))
    assert sorted(results) == ["TOKEN_REVOKED", "ok"]
    assert len(writes) == 1


def test_reset_token_cannot_be_used_as_access(api, mailbox):
    api.post("/api/v1/auth/forgot-password", json={"email": "sv01@whybi.test"})
    assert api.get("/api/v1/me", headers=bearer(mailbox[0][1])).status_code == 401


# --- Phân quyền (Bảng 5.13) --------------------------------------------------------------------


def test_student_calling_lecturer_api_gets_403(api):
    token = login(api, email="sv01@whybi.test").json()["accessToken"]
    r = api.post("/api/v1/classes", headers=bearer(token), json={})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"
    r = api.post(f"/api/v1/tree-versions/{uuid4()}/publish", headers=bearer(token))
    assert r.status_code == 403


def test_lecturer_calling_admin_api_gets_403(api):
    token = login(api).json()["accessToken"]
    assert api.get("/api/v1/admin/users", headers=bearer(token)).status_code == 403


def test_expired_token_gets_401_on_api(api, store):
    gv = store.by_email("gv@whybi.test")
    old = create_access_token(gv.id, gv.role, now=datetime.now(UTC) - timedelta(minutes=31))
    r = api.get("/api/v1/me", headers=bearer(old))
    assert r.status_code == 401 and r.json()["error"]["code"] == "TOKEN_EXPIRED"


PUBLIC = {
    "/api/v1/auth/login",
    "/api/v1/auth/refresh",
    "/api/v1/auth/forgot-password",
    "/api/v1/auth/reset-password",
}


def _depends_on_current_user(dependant) -> bool:
    return any(d.call is deps.get_current_user or _depends_on_current_user(d) for d in dependant.dependencies)


def test_every_api_route_requires_login_except_public():
    """NFR-08: kiểm quyền ở mọi API. Route mới quên gắn Lecturer / Student / AnyUser… sẽ làm đỏ test này."""
    missing = [
        r.path
        for r in app.routes
        if isinstance(r, APIRoute)
        and r.path.startswith("/api/v1/")
        and r.path not in PUBLIC
        and not _depends_on_current_user(r.dependant)
    ]
    assert missing == []


def test_default_jwt_secret_refused_outside_dev(monkeypatch):
    from types import SimpleNamespace

    from app.core import security

    monkeypatch.setattr(
        security, "get_settings", lambda: SimpleNamespace(app_env="prod", jwt_secret=security._DEFAULT_SECRET)
    )
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        security._secret()


def test_password_change_kills_old_refresh_tokens(api, mailbox):
    old = login(api, email="sv01@whybi.test").json()
    api.post("/api/v1/auth/forgot-password", json={"email": "sv01@whybi.test"})
    api.post("/api/v1/auth/reset-password", json={"token": mailbox[0][1], "newPassword": "DatLai2026"})
    r = api.post("/api/v1/auth/refresh", json={"refreshToken": old["refreshToken"]})
    assert r.status_code == 401 and r.json()["error"]["code"] == "TOKEN_REVOKED"


def test_revoke_once_is_atomic():
    import threading

    rev = InMemoryRevocations()
    results: list[bool] = []
    threads = [threading.Thread(target=lambda: results.append(rev.revoke_once("j1", 2**31))) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count(True) == 1


def test_unknown_email_still_spends_hash_time(monkeypatch, store):
    from app.core.errors import AppError
    from app.services import auth as auth_mod

    calls: list[str] = []
    monkeypatch.setattr(auth_mod, "burn_verify_time", calls.append)
    with pytest.raises(AppError):
        auth_mod.AuthService(store, InMemoryRevocations()).login("ai@whybi.test", "x")
    assert calls == ["x"]
