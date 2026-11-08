"""KT-08 – Test bảo mật và phân quyền (FR-AD-01, FR-AD-02; NFR-07, NFR-08, NFR-09; Bảng 5.13).

Phần này KHÔNG cần Postgres / Redis: chạy trong `uv run pytest -q` của CI job backend.
- Kho người dùng và danh sách thu hồi dùng bản trong bộ nhớ (ghi đè dependency như tests/unit/test_auth.py).
- Mọi request đi qua JWT thật (đăng nhập thật hoặc `create_access_token`), không ghi đè `get_current_user`.
Phần cần CSDL (SV A / SV B, GV lớp khác, đồng ý ghi âm) ở test_bao_mat_phan_quyen_db.py.
"""

import base64
import json
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import jwt
import pytest
from argon2 import extract_parameters
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import deps
from app.core import security
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import create_access_token, create_refresh_token, create_reset_token
from app.db.session import get_db
from app.main import app
from app.models.enums import Role
from app.services.auth import InMemoryRevocations, InMemoryUserStore, UserRecord
from app.services.mastery import MasteryService

MAT_KHAU = "Whybi@2026"
_HASH = security.hash_password(MAT_KHAU)  # băm một lần – Argon2 cố ý chậm
GV, SV, QTV = Role.LECTURER, Role.STUDENT, Role.ADMIN

# --- Ma trận phân quyền mong đợi (Bảng 5.13) – viết tay theo đặc tả, KHÔNG suy ra từ code ----------------
# Mỗi route /api/v1 phải có trong bảng; route mới quên khai báo ⇒ test_bang_phan_quyen_phu_moi_route đỏ.
CONG_KHAI = frozenset()  # không cần đăng nhập
BAT_KY = frozenset({GV, SV, QTV})  # đăng nhập là đủ
PHAN_QUYEN: dict[tuple[str, str], frozenset[Role]] = {
    # Xác thực, hồ sơ (FR-AD-01)
    ("POST", "/auth/login"): CONG_KHAI,
    ("POST", "/auth/refresh"): CONG_KHAI,
    ("POST", "/auth/forgot-password"): CONG_KHAI,
    ("POST", "/auth/reset-password"): CONG_KHAI,
    ("POST", "/auth/logout"): BAT_KY,
    ("GET", "/me"): BAT_KY,
    ("PATCH", "/me"): BAT_KY,
    ("GET", "/notifications"): BAT_KY,
    ("POST", "/notifications/read-all"): BAT_KY,
    ("POST", "/notifications/{notification_id}/read"): BAT_KY,
    # Lớp
    ("GET", "/classes"): frozenset({GV, SV}),
    ("POST", "/classes"): frozenset({GV}),
    ("POST", "/classes/join"): frozenset({SV}),
    ("POST", "/classes/{class_id}/syllabi"): frozenset({GV}),
    ("POST", "/classes/{class_id}/archive"): frozenset({GV, QTV}),
    ("POST", "/classes/{class_id}/restore"): frozenset({GV, QTV}),
    # Cây: tạo / sửa / phát hành – GV; xem cây đã phát hành – GV, SV; QTV ✗
    ("GET", "/classes/{class_id}/tree"): frozenset({GV, SV}),
    ("POST", "/classes/{class_id}/tree-versions"): frozenset({GV}),
    ("GET", "/classes/{class_id}/tree-versions"): frozenset({GV}),
    ("POST", "/tree-versions/{version_id}/nodes"): frozenset({GV}),
    ("POST", "/tree-versions/{version_id}/edges"): frozenset({GV}),
    ("POST", "/tree-versions/{version_id}/publish"): frozenset({GV}),
    ("POST", "/tree-versions/{version_id}/restore"): frozenset({GV}),
    ("GET", "/tree-versions/{from_id}/compare/{to_id}"): frozenset({GV}),
    ("PATCH", "/nodes/{node_id}"): frozenset({GV}),
    ("DELETE", "/nodes/{node_id}"): frozenset({GV}),
    ("DELETE", "/edges/{edge_id}"): frozenset({GV}),
    ("PUT", "/nodes/{node_id}/rubric"): frozenset({GV}),
    ("POST", "/nodes/{node_id}/rubric/regenerate"): frozenset({GV}),
    ("GET", "/classes/{class_id}/my-map"): frozenset({SV}),
    # Phiên giảng lại – chỉ SV thực hiện; xem kết quả: GV (SV lớp mình), SV (của mình)
    ("POST", "/sessions"): frozenset({SV}),
    ("GET", "/sessions/{session_id}"): frozenset({SV}),
    ("GET", "/sessions/{session_id}/turns/{turn_no}/tts"): frozenset({SV}),
    ("POST", "/sessions/{session_id}/audio"): frozenset({SV}),
    ("POST", "/sessions/{session_id}/turns"): frozenset({SV}),
    ("POST", "/sessions/{session_id}/timeout"): frozenset({SV}),
    ("POST", "/sessions/{session_id}/abandon"): frozenset({SV}),
    ("GET", "/sessions/{session_id}/result"): frozenset({GV, SV}),
    ("GET", "/me/sessions"): frozenset({SV}),
    ("GET", "/me/sessions/{session_id}"): frozenset({SV}),
    # Nghe lại ghi âm một lượt: GV (SV lớp mình), SV (của mình)
    ("GET", "/turns/{turn_id}/audio"): frozenset({GV, SV}),
    # Bản đồ nhiệt có tên SV, hồ sơ SV, báo cáo – chỉ GV
    ("GET", "/classes/{class_id}/heatmap"): frozenset({GV}),
    ("GET", "/classes/{class_id}/nodes/{node_id}/detail"): frozenset({GV}),
    ("GET", "/classes/{class_id}/students/{student_id}/profile"): frozenset({GV}),
    ("GET", "/classes/{class_id}/settings"): frozenset({GV}),
    ("PUT", "/classes/{class_id}/settings"): frozenset({GV}),
    ("GET", "/classes/{class_id}/report"): frozenset({GV}),
    # Ghép cặp: chạy / điều chỉnh – GV; phản hồi – SV
    ("POST", "/classes/{class_id}/matching-rounds"): frozenset({GV}),
    ("PATCH", "/matches/{match_id}"): frozenset({GV}),
    ("GET", "/classes/{class_id}/matching-stats"): frozenset({GV}),
    ("PUT", "/classes/{class_id}/nodes/{node_id}/review-window"): frozenset({GV}),
    ("GET", "/classes/{class_id}/review-windows"): frozenset({GV}),
    ("GET", "/classes/{class_id}/matches"): frozenset({GV, SV}),  # SV-07 cặp của mình; GV-09 mọi cặp lớp mình
    ("PUT", "/enrollments/{enrollment_id}/peer-opt-in"): frozenset({SV}),
    ("POST", "/matches/{match_id}/{action}"): frozenset({SV}),
    # Quản trị: tài khoản, môn học, cấu hình AI, hạn mức – QTV; cờ vi phạm – GV (lớp mình) + QTV
    ("GET", "/admin/users"): frozenset({QTV}),
    ("POST", "/admin/users"): frozenset({QTV}),
    ("PATCH", "/admin/users/{user_id}"): frozenset({QTV}),
    ("POST", "/admin/users/{user_id}/reset-password"): frozenset({QTV}),
    ("POST", "/admin/users/import"): frozenset({QTV}),
    ("GET", "/admin/courses"): frozenset({QTV}),
    ("POST", "/admin/courses"): frozenset({QTV}),
    ("PUT", "/admin/courses/{course_id}"): frozenset({QTV}),
    ("PUT", "/admin/ai-config"): frozenset({QTV}),
    ("GET", "/admin/quotas"): frozenset({QTV}),
    ("PUT", "/admin/quotas"): frozenset({QTV}),
    ("GET", "/admin/audit-logs"): frozenset({QTV}),
    ("GET", "/admin/flags"): frozenset({GV, QTV}),
    ("POST", "/admin/flags/{flag_id}/resolve"): frozenset({GV, QTV}),
}


def _cac_route_api() -> list[tuple[str, str]]:
    """(method, path không có /api/v1) của mọi route thật.

    FastAPI ≥ 0.140 bọc router con trong `_IncludedRouter` – `app.routes` KHÔNG còn chứa APIRoute của /api/v1,
    nên phải đi xuống `original_router` (kèm prefix) mới thấy đủ.
    """

    def di(routes, prefix: str) -> Iterator[tuple[str, APIRoute]]:
        for r in routes:
            if isinstance(r, APIRoute):
                yield prefix + r.path, r
            elif hasattr(r, "original_router"):
                yield from di(r.original_router.routes, prefix + r.include_context.prefix)

    goc = get_settings().api_prefix
    return sorted(
        (m, path.removeprefix(goc)) for path, r in di(app.routes, "") if path.startswith(goc + "/") for m in r.methods
    )


def _url(path: str) -> str:
    """Điền tham số đường dẫn bằng uuid ngẫu nhiên ({action} → accept)."""
    return "/api/v1" + re.sub(r"\{(\w+)\}", lambda m: "accept" if m[1] == "action" else str(uuid4()), path)


def _goi(api: TestClient, method: str, path: str, headers: dict[str, str] | None = None):
    kwargs = {"json": {}} if method in {"POST", "PUT", "PATCH"} else {}
    return api.request(method, _url(path), headers=headers or {}, **kwargs)


def _ma_loi(r) -> str | None:
    """Mã lỗi AppError nếu thân là JSON `{"error": {...}}`; 204 / 500 thân rỗng hoặc chữ thường ⇒ None."""
    try:
        body = r.json()
    except ValueError:
        return None
    return body.get("error", {}).get("code") if isinstance(body, dict) else None


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- Fixture -------------------------------------------------------------------------------------


@pytest.fixture
def store() -> InMemoryUserStore:
    def u(email: str, role: Role, name: str) -> UserRecord:
        return UserRecord(id=uuid4(), email=email, full_name=name, role=role, password_hash=_HASH, is_active=True)

    return InMemoryUserStore(
        [
            u("gv@whybi.test", GV, "TS. Nguyễn Văn Bình"),
            u("sv01@whybi.test", SV, "Nguyễn Văn An"),
            u("sv02@whybi.test", SV, "Trần Thị Bích"),
            u("admin@whybi.test", QTV, "Quản trị Whybi"),
        ]
    )


@pytest.fixture
def mailbox() -> list[tuple[str, str]]:
    return []


@pytest.fixture
def api(store, mailbox) -> Iterator[TestClient]:
    """API thật, kho người dùng trong bộ nhớ, CSDL là Session không gắn engine (route nào chạm CSDL → 500).
    Không ghi đè get_current_user: mọi quyết định 401 / 403 do JWT thật và require_role."""
    revocations = InMemoryRevocations()
    app.dependency_overrides[deps.get_user_store] = lambda: store
    app.dependency_overrides[deps.get_revocations] = lambda: revocations
    app.dependency_overrides[deps.get_mailer] = lambda: lambda email, token: mailbox.append((email, token))
    app.dependency_overrides[get_db] = lambda: Session()  # không kết nối: không phụ thuộc Postgres trong CI job backend
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


def dang_nhap(api: TestClient, email: str = "gv@whybi.test", password: str = MAT_KHAU) -> dict:
    r = api.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def token_vai(store: InMemoryUserStore, role: Role, **kw) -> str:
    """Access token thật (ký bằng JWT_SECRET) của tài khoản mẫu có vai trò `role`."""
    u = store.by_email({GV: "gv@whybi.test", SV: "sv01@whybi.test", QTV: "admin@whybi.test"}[role])
    return create_access_token(u.id, u.role, u.full_name, **kw)


# --- NFR-07: JWT hết hạn sau 30 phút -------------------------------------------------------------


def _tua_dong_ho(monkeypatch, delta: timedelta) -> None:
    """Giả lập thời gian: đồng hồ mà security.decode_token dùng chạy nhanh thêm `delta`."""
    goc = datetime

    class DongHoNhanh(goc):
        @classmethod
        def now(cls, tz=None):
            return goc.now(tz) + delta

    monkeypatch.setattr(security, "datetime", DongHoNhanh)


def test_cau_hinh_jwt_30_phut():
    assert get_settings().jwt_access_minutes == 30, "NFR-07: access token phải hết hạn sau 30 phút"


def test_token_dang_nhap_con_hieu_luc_o_phut_29(api, monkeypatch):
    body = dang_nhap(api)
    assert body["expiresIn"] == 1800
    _tua_dong_ho(monkeypatch, timedelta(minutes=29, seconds=50))
    assert api.get("/api/v1/me", headers=bearer(body["accessToken"])).status_code == 200


@pytest.mark.parametrize("sau", [timedelta(minutes=30), timedelta(minutes=30, seconds=1), timedelta(hours=5)])
def test_token_dang_nhap_het_han_tu_phut_30(api, monkeypatch, sau):
    token = dang_nhap(api, "sv01@whybi.test")["accessToken"]
    _tua_dong_ho(monkeypatch, sau)
    r = api.get("/api/v1/me", headers=bearer(token))
    assert r.status_code == 401 and r.json()["error"]["code"] == "TOKEN_EXPIRED"


def test_token_het_han_bi_tu_choi_o_moi_api(api, store):
    """Token quá 30 phút: mọi route cần đăng nhập đều 401 TOKEN_EXPIRED (không route nào bỏ qua kiểm hạn)."""
    cu = token_vai(store, GV, now=datetime.now(UTC) - timedelta(minutes=31))
    loi = []
    for method, path in _cac_route_api():
        if PHAN_QUYEN.get((method, path)) == CONG_KHAI:
            continue
        r = _goi(api, method, path, bearer(cu))
        if r.status_code != 401 or r.json()["error"]["code"] != "TOKEN_EXPIRED":
            loi.append((method, path, r.status_code))
    assert loi == []


def test_refresh_sau_30_phut_van_lay_duoc_access_moi(api, monkeypatch):
    """Hết hạn access không bắt đăng nhập lại: refresh (7 ngày) cấp access mới."""
    body = dang_nhap(api)
    _tua_dong_ho(monkeypatch, timedelta(minutes=45))
    r = api.post("/api/v1/auth/refresh", json={"refreshToken": body["refreshToken"]})
    assert r.status_code == 200, r.text
    # Không gọi /me bằng token mới: PyJWT kiểm `iat` theo đồng hồ thật, token sinh ở "tương lai" bị coi chưa hiệu lực.
    moi = jwt.decode(r.json()["accessToken"], options={"verify_signature": False})
    assert moi["exp"] - moi["iat"] == 30 * 60 and r.json()["expiresIn"] == 1800


# --- NFR-07: token sai / giả mạo / thu hồi --------------------------------------------------------


def _b64(obj: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()


def _claims_hop_le(store, role: Role = QTV) -> dict:
    u = store.by_email("sv01@whybi.test")
    now = int(datetime.now(UTC).timestamp())
    return {"sub": str(u.id), "typ": "access", "jti": uuid4().hex, "iat": now, "exp": now + 1800, "role": str(role)}


def test_thieu_token_401(api):
    r = api.get("/api/v1/me")
    assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.parametrize("header", ["Basic Z3Y6V2h5YmlAMjAyNg==", "Bearer", "Token abc", "Bearer    "])
def test_sai_kieu_header_401(api, header):
    assert api.get("/api/v1/me", headers={"Authorization": header}).status_code == 401


@pytest.mark.parametrize(
    "token",
    ["rac", "a.b.c", "eyJhbGciOiJIUzI1NiJ9.e30.", ""],
    ids=["chuoi-rac", "ba-phan-rac", "khong-chu-ky", "rong"],
)
def test_token_rac_401(api, token):
    assert api.get("/api/v1/me", headers=bearer(token)).status_code == 401


def test_token_ky_bang_khoa_khac_401(api, store):
    gia = jwt.encode(_claims_hop_le(store), "khoa-cua-ke-tan-cong-" + "x" * 32, algorithm="HS256")
    r = api.get("/api/v1/admin/users", headers=bearer(gia))
    assert r.status_code == 401 and r.json()["error"]["code"] == "INVALID_TOKEN"


def test_token_alg_none_401(api, store):
    gia = _b64({"alg": "none", "typ": "JWT"}) + "." + _b64(_claims_hop_le(store)) + "."
    r = api.get("/api/v1/admin/users", headers=bearer(gia))
    assert r.status_code == 401 and r.json()["error"]["code"] == "INVALID_TOKEN"


def test_sua_vai_tro_trong_payload_khong_giu_chu_ky_401(api, store):
    """SV lấy token thật, sửa role=ADMIN trong payload, giữ chữ ký cũ ⇒ phải bị từ chối."""
    token = dang_nhap(api, "sv01@whybi.test")["accessToken"]
    header, payload, sig = token.split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    claims["role"] = "ADMIN"
    gia = f"{header}.{_b64(claims)}.{sig}"
    r = api.get("/api/v1/admin/users", headers=bearer(gia))
    assert r.status_code == 401 and r.json()["error"]["code"] == "INVALID_TOKEN"


@pytest.mark.parametrize("thieu", ["sub", "typ", "jti", "exp", "iat", "role"])
def test_token_thieu_claim_401(api, store, thieu):
    claims = _claims_hop_le(store)
    claims.pop(thieu)
    token = jwt.encode(claims, security._secret(), algorithm="HS256")
    r = api.get("/api/v1/me", headers=bearer(token))
    assert r.status_code == 401 and r.json()["error"]["code"] == "INVALID_TOKEN"


def test_vai_tro_la_trong_token_401(api, store):
    claims = _claims_hop_le(store) | {"role": "SUPERADMIN"}
    token = jwt.encode(claims, security._secret(), algorithm="HS256")
    assert api.get("/api/v1/me", headers=bearer(token)).status_code == 401


def test_refresh_va_reset_token_khong_dung_lam_access(api, store):
    u = store.by_email("sv01@whybi.test")
    for token in (create_refresh_token(u.id, u.password_hash), create_reset_token(u.id, u.password_hash)):
        r = api.get("/api/v1/me", headers=bearer(token))
        assert r.status_code == 401 and r.json()["error"]["code"] == "INVALID_TOKEN"


def test_access_token_khong_dung_lam_refresh(api):
    body = dang_nhap(api)
    r = api.post("/api/v1/auth/refresh", json={"refreshToken": body["accessToken"]})
    assert r.status_code == 401


def test_dang_xuat_thu_hoi_access_va_refresh(api):
    body = dang_nhap(api, "sv01@whybi.test")
    h = bearer(body["accessToken"])
    assert api.post("/api/v1/auth/logout", headers=h, json={"refreshToken": body["refreshToken"]}).status_code == 204
    me = api.get("/api/v1/me", headers=h)
    assert me.status_code == 401 and me.json()["error"]["code"] == "TOKEN_REVOKED"
    r = api.post("/api/v1/auth/refresh", json={"refreshToken": body["refreshToken"]})
    assert r.status_code == 401 and r.json()["error"]["code"] == "TOKEN_REVOKED"


def test_dang_xuat_khong_thu_hoi_duoc_refresh_cua_nguoi_khac(api):
    """SV A gửi refresh token của SV B khi đăng xuất ⇒ chỉ phiên của A bị thu hồi, B không bị đá ra."""
    a = dang_nhap(api, "sv01@whybi.test")
    b = dang_nhap(api, "sv02@whybi.test")
    r = api.post("/api/v1/auth/logout", headers=bearer(a["accessToken"]), json={"refreshToken": b["refreshToken"]})
    assert r.status_code == 204
    assert api.post("/api/v1/auth/refresh", json={"refreshToken": b["refreshToken"]}).status_code == 200


def test_refresh_bi_khoa_khi_tai_khoan_bi_khoa(api, store):
    body = dang_nhap(api, "sv01@whybi.test")
    store.by_email("sv01@whybi.test").is_active = False
    assert api.post("/api/v1/auth/refresh", json={"refreshToken": body["refreshToken"]}).status_code == 401
    r = api.post("/api/v1/auth/login", json={"email": "sv01@whybi.test", "password": MAT_KHAU})
    assert r.status_code == 403 and r.json()["error"]["code"] == "ACCOUNT_DISABLED"


@pytest.mark.parametrize(
    "cau_hinh",
    [
        {"allow_dev_tokens": True, "demo_mode": False, "app_env": "prod"},
        {"allow_dev_tokens": True, "demo_mode": False, "app_env": "demo"},
        {"allow_dev_tokens": True, "demo_mode": True, "app_env": "dev"},
        {"allow_dev_tokens": False, "demo_mode": False, "app_env": "dev"},
    ],
    ids=["prod", "demo", "dev-demo-mode", "dev-tat-co"],
)
def test_token_dev_bi_tu_choi_ngoai_dev(api, monkeypatch, cau_hinh):
    """`Bearer dev-admin` là cửa hậu tạm thời: demo / prod / DEMO_MODE=1 / cờ tắt ⇒ phải 401."""
    monkeypatch.setattr(deps, "get_settings", lambda: SimpleNamespace(**cau_hinh))
    r = api.get("/api/v1/admin/users", headers=bearer("dev-admin"))
    assert r.status_code == 401


# --- NFR-07: mật khẩu lưu dạng Argon2id ----------------------------------------------------------


def _la_argon2id_an_toan(h: str, plain: str) -> None:
    assert h.startswith("$argon2id$"), h[:20]
    assert plain not in h
    p = extract_parameters(h)
    # Ngưỡng tối thiểu OWASP cho Argon2id: m ≥ 19 MiB, t ≥ 2, p ≥ 1
    assert p.memory_cost >= 19 * 1024 and p.time_cost >= 2 and p.parallelism >= 1
    assert security.verify_password(plain, h)


def test_ham_bam_la_argon2id_co_muoi():
    a, b = security.hash_password(MAT_KHAU), security.hash_password(MAT_KHAU)
    _la_argon2id_an_toan(a, MAT_KHAU)
    assert a != b, "cùng mật khẩu phải ra hash khác nhau (muối ngẫu nhiên)"


def test_doi_mat_khau_luu_argon2id_khong_plaintext(api, store):
    token = dang_nhap(api, "sv01@whybi.test")["accessToken"]
    moi = "MatKhauMoi#2026"
    r = api.patch("/api/v1/me", headers=bearer(token), json={"currentPassword": MAT_KHAU, "newPassword": moi})
    assert r.status_code == 200, r.text
    _la_argon2id_an_toan(store.by_email("sv01@whybi.test").password_hash, moi)


def test_dat_lai_mat_khau_luu_argon2id(api, store, mailbox):
    api.post("/api/v1/auth/forgot-password", json={"email": "sv02@whybi.test"})
    moi = "DatLai#2026"
    assert api.post("/api/v1/auth/reset-password", json={"token": mailbox[0][1], "newPassword": moi}).status_code == 204
    _la_argon2id_an_toan(store.by_email("sv02@whybi.test").password_hash, moi)


def test_phan_hoi_khong_lo_mat_khau_hay_hash(api):
    body = dang_nhap(api, "sv01@whybi.test")
    h = bearer(body["accessToken"])
    for r in (
        api.get("/api/v1/me", headers=h),
        api.patch("/api/v1/me", headers=h, json={"fullName": "An"}),
    ):
        text = r.text.lower()
        assert r.status_code == 200
        assert "password" not in text and "$argon2" not in text and MAT_KHAU.lower() not in text
    claims = security.decode_token(body["accessToken"], "access")
    assert not {"password", "password_hash", "pwf", "email"} & set(claims)


# --- FR-AD-02, NFR-08: phân quyền theo vai trò (Bảng 5.13) ---------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="lỗi của Long (C2): services/mastery.py my_map gọi _tree() TRƯỚC _require_enrolled ⇒ SV ngoài lớp "
    "nhận 404 TREE_NOT_PUBLISHED (lộ trạng thái cây) thay vì 403 NOT_ENROLLED. Sửa xong thì bỏ dấu xfail.",
)
def test_my_map_sv_ngoai_lop_chua_phat_hanh_bi_403_khong_can_postgres():
    """Không ghi danh + chưa phát hành: phải từ chối quyền, không lộ trạng thái cây."""
    db = Mock(spec=Session)
    db.get.return_value = SimpleNamespace()  # lớp tồn tại
    db.scalars.return_value = []  # SV chưa ghi danh
    db.scalar.return_value = None  # chưa phát hành cây
    with pytest.raises(AppError) as exc:
        MasteryService(db, bus=Mock()).my_map(uuid4(), uuid4())
    assert exc.value.status == 403 and exc.value.code == "NOT_ENROLLED"


def test_bang_phan_quyen_phu_moi_route():
    """Route có trong code mà thiếu trong PHAN_QUYEN (hoặc ngược lại) ⇒ đỏ: phải khai quyền cho route mới."""
    thuc = set(_cac_route_api())
    assert len(thuc) >= 28, "quét route rỗng/thiếu – kiểm lại cách duyệt app.routes"
    assert thuc == set(PHAN_QUYEN)


def test_moi_route_khong_cong_khai_doi_dang_nhap(api):
    loi = []
    for (method, path), vai in PHAN_QUYEN.items():
        if vai == CONG_KHAI:
            continue
        r = _goi(api, method, path)
        if r.status_code != 401 or r.json()["error"]["code"] != "UNAUTHORIZED":
            loi.append((method, path, r.status_code))
    assert loi == []


@pytest.mark.parametrize("vai", [GV, SV, QTV], ids=["GV", "SV", "QTV"])
def test_vai_tro_khong_duoc_phep_bi_403(api, store, vai):
    """Mỗi vai gọi mọi API không dành cho mình ⇒ 403 FORBIDDEN (vd. SV gọi API GV, GV gọi API QTV)."""
    h = bearer(token_vai(store, vai))
    loi = []
    for (method, path), duoc in PHAN_QUYEN.items():
        if duoc == CONG_KHAI or vai in duoc:
            continue
        r = _goi(api, method, path, h)
        if r.status_code != 403 or r.json()["error"]["code"] != "FORBIDDEN":
            loi.append((method, path, r.status_code))
    assert loi == []


@pytest.mark.parametrize("vai", [GV, SV, QTV], ids=["GV", "SV", "QTV"])
def test_vai_tro_duoc_phep_khong_bi_chan_nham(api, store, vai):
    """Vai được phép không bị 401 / 403 FORBIDDEN (route có thể 404 / 501 / 500 vì không có CSDL – không sao)."""
    h = bearer(token_vai(store, vai))
    loi = []
    for (method, path), duoc in PHAN_QUYEN.items():
        if vai not in duoc or path == "/auth/logout":  # logout thu hồi token ⇒ các route sau sẽ 401 (đã test riêng)
            continue
        r = _goi(api, method, path, h)
        code = _ma_loi(r)
        if r.status_code == 401 or code == "FORBIDDEN":
            loi.append((method, path, r.status_code, code))
    assert loi == []


def test_sv_goi_api_gv_bi_403_bang_token_dang_nhap_that(api):
    """Đúng câu "Xong khi" của C2-07 / KT-08 – qua đăng nhập thật, không tạo token tay."""
    h = bearer(dang_nhap(api, "sv01@whybi.test")["accessToken"])
    for method, path in [
        ("POST", "/classes"),
        ("GET", "/classes/{class_id}/heatmap"),
        ("GET", "/classes/{class_id}/students/{student_id}/profile"),
        ("GET", "/classes/{class_id}/report"),
        ("POST", "/tree-versions/{version_id}/publish"),
        ("POST", "/classes/{class_id}/matching-rounds"),
    ]:
        r = _goi(api, method, path, h)
        assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN", (method, path, r.text)


# --- NFR-09: ghi âm có thời hạn ------------------------------------------------------------------


def test_thoi_han_luu_ghi_am_mac_dinh_30_ngay():
    assert get_settings().audio_retention_days == 30


def test_websocket_khong_token_khong_dang_ky_duoc_kenh_ban_do_nhiet(api):
    """Kênh class:{id}:heatmap chứa tên SV ⇒ subscribe không có token hợp lệ phải bị từ chối."""
    with api.websocket_connect("/api/v1/ws") as ws:
        ws.send_json({"action": "subscribe", "channel": f"class:{uuid4()}:heatmap", "token": "rac"})
        msg = ws.receive_json()
    assert msg["event"] == "error" and msg["payload"]["code"] in {"UNAUTHORIZED", "INVALID_TOKEN", "FORBIDDEN"}
