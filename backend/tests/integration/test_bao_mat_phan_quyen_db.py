"""KT-08 – phân quyền THEO LỚP và THEO NGƯỜI trên Postgres thật (NFR-08, NFR-09, BR-13, Bảng 5.13).

Chạy khi có TEST_DATABASE_URL (CI job backend đặt sẵn, CSDL đã `alembic upgrade head`); không có thì bỏ qua.
Mỗi test chạy trong một transaction rollback. Xác thực THẬT: tài khoản băm Argon2id trong bảng `users`,
đăng nhập qua POST /auth/login, không ghi đè `get_current_user`.

Endpoint chưa làm (501) ⇒ test `xfail(strict=True, reason="chờ <mã thẻ>")`: khi thẻ đó xong mà quyền đúng,
test chuyển XPASS và làm đỏ CI ⇒ người làm thẻ bỏ dấu xfail (biến thành test hồi quy).
"""

import json
import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import hash_password, verify_password
from app.db.session import get_db
from app.main import app
from app.models.enums import MasteryState, Role, SessionStatus, Verdict
from app.models.schemas.session import SessionResult
from app.models.session import Evaluation, TeachingSession
from app.models.users import ClassSection, Course, Enrollment, Lecturer, Student, User
from app.realtime.bus import InMemoryEventBus
from app.services.mastery import MasteryService
from app.services.skill_tree import seed_dir

DB_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="đặt TEST_DATABASE_URL để chạy trên Postgres thật")

MAT_KHAU = "Whybi@2026"
_HASH = hash_password(MAT_KHAU) if DB_URL else ""  # băm một lần – Argon2 cố ý chậm
CAY_MAU = json.loads((seed_dir() / "tree_ctdl_gt.json").read_text(encoding="utf-8"))
GOC = "n1_bien_bo_nho"  # nút gốc của cây mẫu – SẴN SÀNG ngay khi phát hành


@dataclass
class NguoiDung:
    id: UUID
    email: str
    ten: str
    headers: dict[str, str] = field(default_factory=dict)


class Lop:
    """Hai lớp: lớp 1 (GV A, SV A + SV B đã tham gia), lớp 2 (GV B). SV C không tham gia lớp nào."""

    def __init__(self, db, api: TestClient):
        self.db, self.api = db, api
        self.gv_a = self._tao(Role.LECTURER, "TS. Lê Văn Chủ")
        self.gv_b = self._tao(Role.LECTURER, "ThS. Phạm Thị Khác")
        self.sv_a = self._tao(Role.STUDENT, "Nguyễn Văn An")
        self.sv_b = self._tao(Role.STUDENT, "Trần Thị Bích")
        self.sv_c = self._tao(Role.STUDENT, "Lý Văn Ngoài")
        course = Course(id=uuid4(), code=uuid4().hex[:8], name="CTDL&GT")
        db.add(course)
        db.flush()
        self.lop1, self.lop2 = uuid4(), uuid4()
        for cid, gv in ((self.lop1, self.gv_a), (self.lop2, self.gv_b)):
            db.add(
                ClassSection(
                    id=cid,
                    course_id=course.id,
                    lecturer_id=gv.id,
                    name=f"Nhóm {cid.hex[:4]}",
                    semester="HK1",
                    join_code=uuid4().hex[:8].upper(),
                )
            )
        db.flush()
        for sv in (self.sv_a, self.sv_b):
            db.add(Enrollment(class_id=self.lop1, student_id=sv.id))
        db.flush()
        for u in (self.gv_a, self.gv_b, self.sv_a, self.sv_b, self.sv_c):
            u.headers = self.dang_nhap(u.email)

    def _tao(self, role: Role, ten: str) -> NguoiDung:
        email = f"kt08.{uuid4().hex[:8]}@whybi.test"
        u = User(id=uuid4(), full_name=ten, email=email, password_hash=_HASH, role=role)
        self.db.add(u)
        self.db.flush()
        if role == Role.LECTURER:
            self.db.add(Lecturer(user_id=u.id))
        else:
            self.db.add(Student(user_id=u.id, student_code=uuid4().hex[:10]))
        self.db.flush()
        return NguoiDung(u.id, email, ten)

    def dang_nhap(self, email: str, password: str = MAT_KHAU) -> dict[str, str]:
        r = self.api.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['accessToken']}"}

    def phat_hanh_cay(self) -> dict:
        """GV A nhập cây mẫu, duyệt mọi rubric, phát hành – bằng token thật của GV A."""
        h = self.gv_a.headers
        r = self.api.post(f"/api/v1/classes/{self.lop1}/tree-versions", json=CAY_MAU, headers=h)
        assert r.status_code == 201, r.text
        tv = r.json()
        rubric = next(n["rubric"] for n in CAY_MAU["nodes"] if n.get("rubric"))
        for n in tv["nodes"]:
            r = self.api.put(f"/api/v1/nodes/{n['id']}/rubric", json=rubric | {"approved": True}, headers=h)
            assert r.status_code == 200, r.text
        r = self.api.post(f"/api/v1/tree-versions/{tv['id']}/publish", headers=h)
        assert r.status_code == 200, r.text
        return r.json()

    def phien(self, sv: NguoiDung, tree: dict, key: str = GOC, input_mode: str = "TEXT") -> UUID:
        s = TeachingSession(
            id=uuid4(),
            student_id=sv.id,
            node_id=UUID(next(n["id"] for n in tree["nodes"] if n["key"] == key)),
            class_id=self.lop1,
            input_mode=input_mode,
            status="CREATED",
        )
        self.db.add(s)
        self.db.flush()
        return s.id


@pytest.fixture
def lop(monkeypatch) -> Iterator[Lop]:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    import app.services.mastery as mastery_mod

    bus = InMemoryEventBus()
    monkeypatch.setattr(mastery_mod, "get_bus", lambda: bus)
    engine = create_engine(DB_URL)
    conn = engine.connect()
    tx = conn.begin()
    db = Session(bind=conn, join_transaction_mode="create_savepoint")
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as api:
        yield Lop(db, api)
    app.dependency_overrides.clear()
    db.close()
    tx.rollback()
    conn.close()
    engine.dispose()


@pytest.fixture
def cay(lop) -> dict:
    return lop.phat_hanh_cay()


def _ma(r) -> str:
    return r.json()["error"]["code"]


# --- NFR-07: mật khẩu trong bảng users là Argon2id ------------------------------------------------


def test_doi_mat_khau_luu_argon2id_trong_csdl(lop):
    moi = "MatKhauMoi#2026"
    r = lop.api.patch("/api/v1/me", headers=lop.sv_a.headers, json={"currentPassword": MAT_KHAU, "newPassword": moi})
    assert r.status_code == 200, r.text
    h = lop.db.scalar(select(User.password_hash).where(User.id == lop.sv_a.id))
    assert h.startswith("$argon2id$") and moi not in h and verify_password(moi, h)
    assert lop.dang_nhap(lop.sv_a.email, moi)


def test_khong_cot_nao_cua_users_chua_mat_khau_ro(lop):
    """Không lưu mật khẩu rõ ở bất kỳ cột nào của bảng users."""
    row = lop.db.execute(select(User.__table__).where(User.id == lop.sv_a.id)).mappings().one()
    assert all(MAT_KHAU not in str(v) for v in row.values())


# --- NFR-08: chỉ GV phụ trách lớp xem / sửa dữ liệu lớp ------------------------------------------


def test_gv_lop_khac_khong_xem_duoc_cay_cua_lop(lop, cay):
    url = f"/api/v1/classes/{lop.lop1}/tree"
    assert lop.api.get(url, headers=lop.gv_a.headers).status_code == 200
    for params in ({}, {"draft": "true"}):
        r = lop.api.get(url, headers=lop.gv_b.headers, params=params)
        assert r.status_code == 403 and _ma(r) == "NOT_CLASS_OWNER", params


def test_gv_lop_khac_khong_sua_duoc_cay(lop, cay):
    h = lop.gv_b.headers
    node = cay["nodes"][0]
    rubric = next(n["rubric"] for n in CAY_MAU["nodes"] if n.get("rubric"))
    for r in (
        lop.api.post(f"/api/v1/classes/{lop.lop1}/tree-versions", headers=h),
        lop.api.post(f"/api/v1/tree-versions/{cay['id']}/publish", headers=h),
        lop.api.patch(f"/api/v1/nodes/{node['id']}", headers=h, json={"title": "Bị sửa trộm"}),
        lop.api.put(f"/api/v1/nodes/{node['id']}/rubric", headers=h, json=rubric),
        lop.api.delete(f"/api/v1/edges/{cay['edges'][0]['id']}", headers=h),
    ):
        assert r.status_code == 403 and _ma(r) == "NOT_CLASS_OWNER", (r.request.url, r.text)


def test_sv_khong_ep_duoc_ban_nhap_bang_draft_true(lop, cay):
    """SV gửi draft=true vẫn chỉ nhận bản đã phát hành (không lộ bản nháp GV đang sửa)."""
    assert lop.api.post(f"/api/v1/classes/{lop.lop1}/tree-versions", headers=lop.gv_a.headers).status_code == 201
    r = lop.api.get(f"/api/v1/classes/{lop.lop1}/tree", headers=lop.sv_a.headers, params={"draft": "true"})
    assert r.status_code == 200 and r.json()["id"] == cay["id"] and r.json()["status"] == "PUBLISHED"


def test_sv_ngoai_lop_khong_xem_duoc_cay_va_ban_do(lop, cay):
    for url in (f"/api/v1/classes/{lop.lop1}/tree", f"/api/v1/classes/{lop.lop1}/my-map"):
        r = lop.api.get(url, headers=lop.sv_c.headers)
        assert r.status_code == 403 and _ma(r) == "NOT_ENROLLED", url


# --- NFR-08: SV không xem được kết quả của nhau --------------------------------------------------


def _qua_nut(lop: Lop, sv: NguoiDung, tree: dict, key: str = GOC) -> UUID:
    """SV qua một nút – ghi ma trận thành thạo qua MasteryService (đúng luật kiến trúc)."""
    svc = MasteryService(lop.db)
    sid = lop.phien(sv, tree, key)
    node_id = UUID(next(n["id"] for n in tree["nodes"] if n["key"] == key))
    svc.start_session(sv.id, node_id, sid)
    svc.apply_result(
        SessionResult(
            session_id=sid,
            student_id=sv.id,
            node_id=node_id,
            class_id=lop.lop1,
            state=MasteryState.MASTERED,
            verdict=Verdict.PASSED,
            total_score=91.0,
            criteria=[],
        )
    )
    session = lop.db.get(TeachingSession, sid)
    session.status = SessionStatus.COMPLETED
    session.ended_at = datetime.now(UTC)
    lop.db.add(Evaluation(session_id=sid, total_score=91.0, verdict=Verdict.PASSED))
    lop.db.flush()
    return sid


def test_my_map_chi_tra_du_lieu_cua_chinh_minh(lop, cay):
    _qua_nut(lop, lop.sv_b, cay)
    url = f"/api/v1/classes/{lop.lop1}/my-map"
    b = lop.api.get(url, headers=lop.sv_b.headers).json()
    assert b["studentId"] == str(lop.sv_b.id) and b["masteredCount"] == 1

    a = lop.api.get(url, headers=lop.sv_a.headers)
    assert a.status_code == 200
    body = a.json()
    assert body["studentId"] == str(lop.sv_a.id) and body["masteredCount"] == 0
    n1 = next(p for p in body["progress"] if p["nodeKey"] == GOC)
    assert n1["state"] == "AVAILABLE" and n1["bestScore"] is None and n1["attempts"] == 0
    for lo in (str(lop.sv_b.id), lop.sv_b.email, lop.sv_b.ten):
        assert lo not in a.text, f"bản đồ của SV A lộ thông tin SV B: {lo}"


@pytest.mark.parametrize("ten_tham_so", ["studentId", "student_id", "userId"])
def test_my_map_bo_qua_tham_so_doi_nguoi(lop, cay, ten_tham_so):
    """SV A thêm ?studentId=<B> để xem bản đồ của B ⇒ vẫn chỉ nhận bản đồ của A."""
    _qua_nut(lop, lop.sv_b, cay)
    r = lop.api.get(
        f"/api/v1/classes/{lop.lop1}/my-map", headers=lop.sv_a.headers, params={ten_tham_so: str(lop.sv_b.id)}
    )
    assert r.status_code == 200 and r.json()["studentId"] == str(lop.sv_a.id) and r.json()["masteredCount"] == 0


def test_sv_ngoai_lop_my_map_lop_chua_phat_hanh_bi_403(lop):
    r = lop.api.get(f"/api/v1/classes/{lop.lop1}/my-map", headers=lop.sv_c.headers)
    assert r.status_code == 403 and _ma(r) == "NOT_ENROLLED"


def test_sv_khong_xem_duoc_ket_qua_phien_cua_sv_khac(lop, cay):
    sid = lop.phien(lop.sv_a, cay)
    r = lop.api.get(f"/api/v1/sessions/{sid}/result", headers=lop.sv_b.headers)
    assert r.status_code == 403 and _ma(r) == "FORBIDDEN"  # TC16


def test_gv_lop_khac_khong_xem_duoc_ket_qua_phien(lop, cay):
    sid = lop.phien(lop.sv_a, cay)
    r = lop.api.get(f"/api/v1/sessions/{sid}/result", headers=lop.gv_b.headers)
    assert r.status_code == 403


def test_sv_khong_gui_duoc_luot_vao_phien_cua_sv_khac(lop, cay):
    sid = lop.phien(lop.sv_a, cay)
    r = lop.api.post(f"/api/v1/sessions/{sid}/turns", headers=lop.sv_b.headers, json={"text": "Con trỏ là ..."})
    assert r.status_code == 403


@pytest.mark.xfail(strict=True, reason="chờ C2-20: GET /me/sessions chưa làm (501)")
def test_lich_su_phien_chi_co_phien_cua_minh(lop, cay):
    sid = _qua_nut(lop, lop.sv_a, cay)
    _qua_nut(lop, lop.sv_b, cay)
    r = lop.api.get("/api/v1/me/sessions", headers=lop.sv_a.headers, params={"classId": str(lop.lop1)})
    assert r.status_code == 200
    assert {s["sessionId"] for s in r.json()} == {str(sid)}
    assert all(s["studentId"] == str(lop.sv_a.id) for s in r.json())


# --- NFR-08: dữ liệu CÓ TÊN SV chỉ GV phụ trách lớp xem được -------------------------------------


@pytest.mark.xfail(strict=True, reason="chờ C2-13: bản đồ nhiệt chưa làm (501)")
def test_gv_lop_khac_khong_xem_duoc_ban_do_nhiet_co_ten(lop, cay):
    r = lop.api.get(f"/api/v1/classes/{lop.lop1}/heatmap", headers=lop.gv_b.headers)
    assert r.status_code == 403
    assert lop.sv_a.ten not in r.text


@pytest.mark.xfail(strict=True, reason="chờ C2-13: chi tiết nút (danh sách SV kẹt) chưa làm (501)")
def test_gv_lop_khac_khong_xem_duoc_chi_tiet_nut(lop, cay):
    r = lop.api.get(f"/api/v1/classes/{lop.lop1}/nodes/{cay['nodes'][0]['id']}/detail", headers=lop.gv_b.headers)
    assert r.status_code == 403


@pytest.mark.xfail(strict=True, reason="chờ C2-17: hồ sơ SV chưa làm (501)")
def test_gv_lop_khac_khong_xem_duoc_ho_so_sv(lop, cay):
    r = lop.api.get(f"/api/v1/classes/{lop.lop1}/students/{lop.sv_a.id}/profile", headers=lop.gv_b.headers)
    assert r.status_code == 403
    assert lop.sv_a.ten not in r.text


@pytest.mark.xfail(strict=True, reason="chờ C2-17: hồ sơ SV chưa làm (501)")
def test_gv_khong_xem_duoc_ho_so_sv_khong_thuoc_lop_minh(lop, cay):
    """GV A hỏi hồ sơ SV C (không thuộc lớp 1) qua lớp của mình ⇒ không được trả tên / kết quả."""
    ok = lop.api.get(f"/api/v1/classes/{lop.lop1}/students/{lop.sv_a.id}/profile", headers=lop.gv_a.headers)
    assert ok.status_code == 200 and lop.sv_a.ten in ok.text
    r = lop.api.get(f"/api/v1/classes/{lop.lop1}/students/{lop.sv_c.id}/profile", headers=lop.gv_a.headers)
    # 404 hợp lệ khi quan hệ SV–lớp không tồn tại; request trên chứng minh route hoạt động.
    assert r.status_code in (403, 404)
    assert lop.sv_c.ten not in r.text


@pytest.mark.xfail(strict=True, reason="chờ C2-20: xuất báo cáo lớp chưa làm (501)")
def test_gv_lop_khac_khong_xuat_duoc_bao_cao(lop, cay):
    r = lop.api.get(f"/api/v1/classes/{lop.lop1}/report", headers=lop.gv_b.headers, params={"format": "csv"})
    assert r.status_code == 403


@pytest.mark.xfail(strict=True, reason="chờ C2-13: GV phụ trách lớp xem được bản đồ nhiệt có tên SV (BR-07)")
def test_gv_phu_trach_xem_duoc_ban_do_nhiet_co_ten(lop, cay):
    r = lop.api.get(f"/api/v1/classes/{lop.lop1}/heatmap", headers=lop.gv_a.headers)
    assert r.status_code == 200 and lop.sv_a.ten in r.text


# --- NFR-09, BR-13: ghi âm chỉ khi SV đồng ý ----------------------------------------------------


@pytest.mark.parametrize("consent", [None, "false", "true"])
def test_ghi_am_chi_duoc_luu_khi_chu_phien_dong_y(lop, cay, consent):
    from app.ai.providers.stt import FakeSTTProvider
    from app.api.sessions import get_speech_service
    from app.services.speech import MemoryAudioStore, SpeechService

    store = MemoryAudioStore()
    app.dependency_overrides[get_speech_service] = lambda: SpeechService(stt=FakeSTTProvider(), store=store)
    sid = lop.phien(lop.sv_a, cay, input_mode="VOICE")
    lop.db.get(TeachingSession, sid).status = "EXPLAINING"
    lop.db.flush()
    response = lop.api.post(
        f"/api/v1/sessions/{sid}/audio",
        headers=lop.sv_a.headers,
        files={"file": ("recording.webm", b"\x1a\x45\xdf\xa3" + b"\0" * 64, "audio/webm")},
        data={} if consent is None else {"consent": consent},
    )
    assert response.status_code == 200, response.text
    if consent == "true":
        assert len(store.objects) == 1
        assert response.json()["audioRef"].startswith("s3://")
    else:
        assert store.objects == {}
        assert response.json()["audioRef"].startswith("unsaved:")


def test_khong_tai_ghi_am_vao_phien_cua_sv_khac(lop, cay):
    sid = lop.phien(lop.sv_a, cay, input_mode="VOICE")
    r = lop.api.post(
        f"/api/v1/sessions/{sid}/audio",
        headers=lop.sv_b.headers,
        files={"file": ("x.webm", b"\x1a\x45\xdf\xa3fake-webm", "audio/webm")},
    )
    assert r.status_code == 403
