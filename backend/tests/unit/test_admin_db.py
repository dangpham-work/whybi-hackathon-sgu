"""C2-18 – Xong khi: nhập CSV 30 SV thành công; vượt hạn mức thì phiên bị chặn có thông báo (FR-AD-03, 04, 06, 07)."""

import io
import wave
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.enums import Role
from app.models.peer import AuditLog
from app.models.session import SecurityFlag, TeachingSession
from app.models.users import User
from app.services.quota import QuotaService
from tests.unit.test_session_orchestrator_db import (  # noqa: F401
    ROOT,
    bus,
    completed,
    node_id,
    published,
    start,
    turn,
    world,
)
from tests.unit.test_tree_edit_db import DB_URL

pytestmark = pytest.mark.skipif(not DB_URL, reason="đặt TEST_DATABASE_URL để chạy trên Postgres thật")


def _audio_chua_cai() -> bool:
    """Endpoint /sessions/{id}/audio còn là bản khung (NotImplementedYet C1-12) thì chưa kiểm hạn mức ghi âm được."""
    import inspect

    from app.api import sessions as sessions_api

    return "NotImplementedYet" in inspect.getsource(sessions_api.upload_audio)


cho_c1_12 = pytest.mark.skipif(_audio_chua_cai(), reason="cần C1-12 (endpoint /audio); tự chạy lại khi C1-12 vào main")

API = "/api/v1"


@pytest.fixture
def admin(world):  # noqa: F811
    u = User(id=uuid4(), full_name="QTV", email=f"{uuid4().hex[:8]}@whybi.test", password_hash="x", role=Role.ADMIN)
    world.db.add(u)
    world.db.flush()
    world.roles[u.id] = Role.ADMIN
    world.admin = u.id
    world.current = u.id
    return world


def csv_file(rows: list[str], header="mssv,ho_ten,email,khoa") -> dict:
    return {"file": ("sv.csv", "\n".join([header, *rows]).encode("utf-8"), "text/csv")}


def thirty() -> list[str]:
    return [f"SV{i:04d},Nguyễn Văn {i},sv{i:04d}@sgu.test,K23" for i in range(30)]


# --- Nhập CSV ------------------------------------------------------------------------------------


def test_nhap_csv_30_sv_thanh_cong_va_dang_nhap_duoc(admin):
    r = admin.api.post(f"{API}/admin/users/import", files=csv_file(thirty()))
    assert r.status_code == 201, r.text
    body = r.json()
    assert len(body["created"]) == 30 and body["skipped"] == [] and body["errors"] == []
    assert len({c["password"] for c in body["created"]}) == 30 and all(
        len(c["password"]) >= 10 for c in body["created"]
    )
    first = body["created"][0]
    login = admin.api.post(f"{API}/auth/login", json={"email": first["email"], "password": first["password"]})
    assert login.status_code == 200 and login.json()["accessToken"]
    listed = admin.api.get(f"{API}/admin/users", params={"role": "STUDENT", "q": "SV0007"}).json()
    assert [u["studentCode"] for u in listed] == ["SV0007"]


def test_nhap_lai_bo_qua_tai_khoan_co_san_va_bao_dong_sai(admin):
    admin.api.post(f"{API}/admin/users/import", files=csv_file(thirty()[:2]))
    rows = [
        "SV0000,Trùng MSSV,khac@sgu.test,K23",  # MSSV đã có
        "SV9000,Trùng email,sv0001@sgu.test,K23",  # email đã có
        "SV9001,,thieu.ten@sgu.test,K23",  # thiếu họ tên
        "SV9002,Email hỏng,khong-phai-email,K23",
        "SV9003,Mới,moi@sgu.test,K23",
        "SV9003,Trùng trong tệp,moi2@sgu.test,K23",
    ]
    body = admin.api.post(f"{API}/admin/users/import", files=csv_file(rows)).json()
    assert [c["studentCode"] for c in body["created"]] == ["SV9003"]
    assert sorted(i["row"] for i in body["skipped"]) == [2, 3]
    assert sorted(i["row"] for i in body["errors"]) == [4, 5, 7]


def test_csv_thieu_cot_422_va_khong_phai_utf8(admin):
    r = admin.api.post(f"{API}/admin/users/import", files=csv_file(["a,b"], header="mssv,ho_ten"))
    assert r.status_code == 422 and r.json()["error"]["code"] == "CSV_MISSING_COLUMNS"
    bad = {"file": ("sv.csv", "mssv,ho_ten,email\nSV1,Nguyễn,a@b.co".encode("utf-16"), "text/csv")}
    assert admin.api.post(f"{API}/admin/users/import", files=bad).status_code == 422


@pytest.mark.parametrize("who", ["gv", "sv"])
def test_chi_qtv_vao_duoc_quan_tri(admin, who):
    admin.current = getattr(admin, who)
    for method, path in [
        ("get", "/admin/users"),
        ("get", "/admin/courses"),
        ("get", "/admin/quotas"),
        ("get", "/admin/audit-logs"),
        ("put", "/admin/quotas"),
    ]:
        assert getattr(admin.api, method)(f"{API}{path}").status_code == 403, path


# --- Tài khoản -----------------------------------------------------------------------------------


def test_tao_khoa_va_dat_lai_mat_khau(admin):
    r = admin.api.post(
        f"{API}/admin/users",
        json={"fullName": "GV Mới", "email": "GV.Moi@Sgu.Test", "role": "LECTURER"},
    )
    assert r.status_code == 201, r.text
    uid, pw = r.json()["user"]["id"], r.json()["password"]
    assert r.json()["user"]["email"] == "gv.moi@sgu.test"
    assert admin.api.post(f"{API}/auth/login", json={"email": "gv.moi@sgu.test", "password": pw}).status_code == 200
    assert (
        admin.api.post(
            f"{API}/admin/users", json={"fullName": "x", "email": "gv.moi@sgu.test", "role": "LECTURER"}
        ).status_code
        == 409
    )
    assert (
        admin.api.post(
            f"{API}/admin/users", json={"fullName": "x", "email": "sv@sgu.test", "role": "STUDENT"}
        ).status_code
        == 422
    )

    assert admin.api.patch(f"{API}/admin/users/{uid}", json={"isActive": False}).json()["isActive"] is False
    assert admin.api.post(f"{API}/auth/login", json={"email": "gv.moi@sgu.test", "password": pw}).status_code in (
        401,
        403,
    )
    new_pw = admin.api.post(f"{API}/admin/users/{uid}/reset-password").json()["password"]
    admin.api.patch(f"{API}/admin/users/{uid}", json={"isActive": True})
    assert admin.api.post(f"{API}/auth/login", json={"email": "gv.moi@sgu.test", "password": new_pw}).status_code == 200


def test_khong_tu_khoa_chinh_minh_va_nhat_ky_khong_lo_mat_khau(admin):
    r = admin.api.patch(f"{API}/admin/users/{admin.admin}", json={"isActive": False})
    assert r.status_code == 409 and r.json()["error"]["code"] == "CANNOT_DEACTIVATE_SELF"
    created = admin.api.post(
        f"{API}/admin/users", json={"fullName": "A", "email": "a@sgu.test", "role": "LECTURER"}
    ).json()
    logs = admin.api.get(f"{API}/admin/audit-logs").json()
    assert logs[0]["action"] == "USER_CREATE" and logs[0]["userId"] == str(admin.admin)
    assert created["password"] not in str(logs)


# --- Danh mục môn học ----------------------------------------------------------------------------


def test_danh_muc_mon_hoc(admin):
    r = admin.api.post(f"{API}/admin/courses", json={"code": "CS999", "name": "Môn thử", "credits": 3})
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    assert admin.api.post(f"{API}/admin/courses", json={"code": "cs999", "name": "Trùng"}).status_code == 409
    assert (
        admin.api.put(f"{API}/admin/courses/{cid}", json={"code": "CS999", "name": "Đã đổi"}).json()["name"] == "Đã đổi"
    )
    assert admin.api.put(f"{API}/admin/courses/{uuid4()}", json={"code": "ZZ", "name": "x"}).status_code == 404
    assert "CS999" in [c["code"] for c in admin.api.get(f"{API}/admin/courses").json()]


# --- Hạn mức -------------------------------------------------------------------------------------


def test_dat_xem_va_bo_han_muc(admin):
    body = {"scope": "CLASS", "scopeId": str(admin.class_id), "tokenLimit": 1000, "audioMinutesLimit": 30}
    r = admin.api.put(f"{API}/admin/quotas", json=body)
    assert r.status_code == 200 and r.json()["name"] and r.json()["tokensUsed"] == 0
    assert [q["tokenLimit"] for q in admin.api.get(f"{API}/admin/quotas", params={"scope": "CLASS"}).json()] == [1000]
    assert admin.api.put(f"{API}/admin/quotas", json=body | {"tokenLimit": -1}).status_code == 422
    assert admin.api.put(f"{API}/admin/quotas", json=body | {"scopeId": str(uuid4())}).status_code == 404
    admin.api.put(f"{API}/admin/quotas", json=body | {"tokenLimit": None, "audioMinutesLimit": None})
    assert admin.api.get(f"{API}/admin/quotas").json() == []


def test_vuot_han_muc_token_chan_bat_dau_phien_co_thong_bao(published):  # noqa: F811
    w, tree = published
    qs = QuotaService(w.db)
    from app.models.schemas.admin import QuotaIn

    qs.set(QuotaIn(scope="CLASS", scope_id=w.class_id, token_limit=100))
    ok = start(w, tree)
    assert ok.status_code == 201, ok.text  # chưa dùng token nào đáng kể (LLM giả)
    sess = w.db.scalar(select(TeachingSession).where(TeachingSession.student_id == w.sv))
    qs.record_tokens(sess.id, w.sv, w.class_id, 500)  # phiên này đã dùng 500 token, vượt 100
    w.db.flush()

    blocked = start(w, tree, key="n2_mang")
    assert blocked.status_code == 429, blocked.text
    err = blocked.json()["error"]
    assert err["code"] == "QUOTA_EXCEEDED" and "hạn mức" in err["message"]
    assert err["details"]["kind"] == "TOKENS" and err["details"]["limit"] == 100 and err["details"]["used"] == 500
    # đang giữa phiên cũng bị chặn gửi tiếp
    assert turn(w, ok.json()["sessionId"], "Biến là vùng nhớ").status_code == 429


def test_han_muc_theo_sv_khong_anh_huong_sv_khac(published):  # noqa: F811
    w, tree = published
    from app.models.schemas.admin import QuotaIn

    qs = QuotaService(w.db)
    qs.set(QuotaIn(scope="STUDENT", scope_id=w.sv, token_limit=0))  # 0 = cấm hẳn
    assert start(w, tree).status_code == 429
    qs.set(QuotaIn(scope="STUDENT", scope_id=w.sv_out, token_limit=0))
    qs.set(QuotaIn(scope="STUDENT", scope_id=w.sv, token_limit=None, audio_minutes_limit=None))
    assert start(w, tree).status_code == 201


def _wav(seconds: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as f:
        f.setnchannels(1), f.setsampwidth(2), f.setframerate(8000)
        f.writeframes(b"\x00\x00" * 8000 * seconds)
    return buf.getvalue()


@cho_c1_12
def test_vuot_han_muc_phut_ghi_am_chan_tai_len(published):  # noqa: F811
    w, tree = published
    from app.models.schemas.admin import QuotaIn

    sid = start(w, tree).json()["sessionId"]
    QuotaService(w.db).set(QuotaIn(scope="CLASS", scope_id=w.class_id, audio_minutes_limit=1))
    sess = w.db.scalar(select(TeachingSession).where(TeachingSession.id == sid))
    QuotaService(w.db).add_audio(sess.id, w.sv, w.class_id, 60)  # đã ghi đủ 1 phút
    w.db.flush()
    r = w.api.post(
        f"{API}/sessions/{sid}/audio", files={"file": ("a.wav", _wav(2), "audio/wav")}, data={"consent": "false"}
    )
    assert r.status_code == 429 and r.json()["error"]["details"]["kind"] == "AUDIO_MINUTES"
    # gõ chữ vẫn được: hạn mức phút ghi âm không chặn token
    assert turn(w, sid, "Biến là vùng nhớ có tên").status_code == 200


@cho_c1_12
def test_tai_ghi_am_cong_thoi_luong_vao_muc_dung(published):  # noqa: F811
    w, tree = published
    from app.models.schemas.admin import QuotaIn

    sid = start(w, tree).json()["sessionId"]
    QuotaService(w.db).set(QuotaIn(scope="CLASS", scope_id=w.class_id, audio_minutes_limit=10))
    r = w.api.post(
        f"{API}/sessions/{sid}/audio", files={"file": ("a.wav", _wav(3), "audio/wav")}, data={"consent": "false"}
    )
    assert r.status_code in (200, 422), r.text  # STT giả có thể không nhận ra lời, nhưng phải qua cổng hạn mức
    if r.status_code == 200:
        used = QuotaService(w.db).usage("CLASS", w.class_id)[1]
        assert used == 3


# --- Cờ vi phạm ----------------------------------------------------------------------------------


@pytest.fixture
def co_co(published):  # noqa: F811
    w, tree = published
    sid = start(w, tree).json()["sessionId"]
    sess = w.db.scalar(select(TeachingSession).where(TeachingSession.id == sid))
    flag = SecurityFlag(session_id=sess.id, type="JAILBREAK", severity="HIGH", detail="bỏ qua mọi chỉ dẫn")
    w.db.add(flag)
    w.db.flush()
    u = User(id=uuid4(), full_name="QTV", email=f"{uuid4().hex[:8]}@whybi.test", password_hash="x", role=Role.ADMIN)
    w.db.add(u)
    w.db.flush()
    w.roles[u.id] = Role.ADMIN
    w.admin = u.id
    return w, flag


def test_qtv_va_gv_phu_trach_thay_co_gv_khac_khong(co_co):
    w, flag = co_co
    for who in (w.admin, w.gv):
        w.current = who
        [f] = w.api.get(f"{API}/admin/flags").json()
        assert f["id"] == str(flag.id) and f["type"] == "JAILBREAK" and f["studentName"] == "SV trong lớp"
    w.current = w.gv_other
    assert w.api.get(f"{API}/admin/flags").json() == []
    assert w.api.post(f"{API}/admin/flags/{flag.id}/resolve").status_code == 404
    w.current = w.sv
    assert w.api.get(f"{API}/admin/flags").status_code == 403


def test_xu_ly_co_ghi_nhat_ky(co_co):
    w, flag = co_co
    w.current = w.gv
    r = w.api.post(f"{API}/admin/flags/{flag.id}/resolve")
    assert r.status_code == 200 and r.json()["resolved"] is True and r.json()["resolvedBy"] == str(w.gv)
    assert w.api.get(f"{API}/admin/flags").json() == []
    assert len(w.api.get(f"{API}/admin/flags", params={"resolved": "true"}).json()) == 1
    assert w.db.scalar(select(AuditLog).where(AuditLog.action == "FLAG_RESOLVE", AuditLog.entity_id == flag.id))


# --- Thu hồi phiên đăng nhập khi khóa / đặt lại mật khẩu -----------------------------------------


def test_khoa_tai_khoan_thu_hoi_ngay_access_token(admin):
    from app.api import deps
    from app.main import app

    created = admin.api.post(
        f"{API}/admin/users", json={"fullName": "GV X", "email": "gvx@sgu.test", "role": "LECTURER"}
    ).json()
    uid, pw = created["user"]["id"], created["password"]
    tok = admin.api.post(f"{API}/auth/login", json={"email": "gvx@sgu.test", "password": pw}).json()["accessToken"]
    # xác thực thật (bỏ ghi đè get_current_user) để thử token
    app.dependency_overrides.pop(deps.get_current_user)
    me = lambda t: admin.api.get(f"{API}/me", headers={"Authorization": f"Bearer {t}"})  # noqa: E731
    assert me(tok).status_code == 200
    app.dependency_overrides[deps.get_current_user] = lambda: deps.CurrentUser(id=admin.admin, role=Role.ADMIN)
    admin.api.patch(f"{API}/admin/users/{uid}", json={"isActive": False})
    app.dependency_overrides.pop(deps.get_current_user)
    r = me(tok)
    assert r.status_code == 401 and r.json()["error"]["code"] == "TOKEN_REVOKED"
    app.dependency_overrides[deps.get_current_user] = lambda: deps.CurrentUser(id=admin.admin, role=Role.ADMIN)


def test_dat_lai_mat_khau_thu_hoi_access_token_cu_nhung_dang_nhap_moi_duoc(admin):
    from app.api import deps
    from app.main import app

    created = admin.api.post(
        f"{API}/admin/users", json={"fullName": "GV Y", "email": "gvy@sgu.test", "role": "LECTURER"}
    ).json()
    uid, pw = created["user"]["id"], created["password"]
    old = admin.api.post(f"{API}/auth/login", json={"email": "gvy@sgu.test", "password": pw}).json()["accessToken"]
    new_pw = admin.api.post(f"{API}/admin/users/{uid}/reset-password").json()["password"]
    new = admin.api.post(f"{API}/auth/login", json={"email": "gvy@sgu.test", "password": new_pw}).json()["accessToken"]
    app.dependency_overrides.pop(deps.get_current_user)
    try:
        assert admin.api.get(f"{API}/me", headers={"Authorization": f"Bearer {old}"}).status_code == 401
        assert admin.api.get(f"{API}/me", headers={"Authorization": f"Bearer {new}"}).status_code == 200
    finally:
        app.dependency_overrides[deps.get_current_user] = lambda: deps.CurrentUser(id=admin.admin, role=Role.ADMIN)


@cho_c1_12
def test_tai_ghi_am_tinh_han_muc_truoc_stt_ke_ca_khi_stt_loi(published):  # noqa: F811
    """Tệp ghi âm bị tính ngay cả khi nhận dạng thất bại (không thể gửi tệp lỗi để né hạn mức)."""
    w, tree = published
    from app.models.schemas.admin import QuotaIn

    sid = start(w, tree).json()["sessionId"]
    QuotaService(w.db).set(QuotaIn(scope="CLASS", scope_id=w.class_id, audio_minutes_limit=10))
    r = w.api.post(
        f"{API}/sessions/{sid}/audio", files={"file": ("a.wav", _wav(3), "audio/wav")}, data={"consent": "false"}
    )
    assert r.status_code in (200, 422), r.text  # STT giả có thể không nhận ra lời nói
    assert QuotaService(w.db).usage("CLASS", w.class_id)[1] == 3


def test_thu_hoi_khong_ho_trong_cung_mot_giay(admin):
    """Token cấp ngay trước khi khóa (cùng giây) cũng bị thu hồi; token cấp ngay sau thì dùng được."""
    from datetime import UTC, datetime

    from app.api import deps
    from app.core.security import create_access_token
    from app.services.auth import InMemoryRevocations

    rev = InMemoryRevocations()
    uid = uuid4()
    before = create_access_token(uid, Role.LECTURER)
    rev.revoke_user(str(uid), datetime.now(UTC).timestamp())
    after = create_access_token(uid, Role.LECTURER)
    with pytest.raises(Exception) as e:
        deps.user_from_token(before, rev)
    assert "TOKEN_REVOKED" in str(getattr(e.value, "code", e.value)) or getattr(e.value, "status_code", 0) == 401
    assert deps.user_from_token(after, rev).id == uid


def test_uoc_luong_thoi_luong_nen_bao_thu():
    from app.services.quota import estimate_audio_seconds

    assert estimate_audio_seconds(b"x" * 60_000, "webm") == 30  # sàn 16 kbps ⇒ tính nhiều hơn thực tế 32 kbps (15 giây)
    assert estimate_audio_seconds(b"x" * 80_000, "mp3") == 10
