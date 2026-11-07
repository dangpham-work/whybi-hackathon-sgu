"""KT-08 – phân quyền THEO LỚP và THEO NGƯỜI trên Postgres thật (NFR-08, NFR-09, BR-13, Bảng 5.13).

Chạy khi có TEST_DATABASE_URL (CI job backend đặt sẵn, CSDL đã `alembic upgrade head`); không có thì bỏ qua.
Mỗi test chạy trong một transaction rollback. Xác thực THẬT: tài khoản băm Argon2id trong bảng `users`,
đăng nhập qua POST /auth/login, không ghi đè `get_current_user`.

STT dùng LLM_MODE=fake; kho âm thanh trong bộ nhớ. API, kiểm quyền, JWT và CSDL dùng mã thật.
Không cần micro / MinIO; không chứng minh HTTPS, mã hóa lưu trữ hay chất lượng STT trên bản deploy.
"""

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password, verify_password
from app.db.session import get_db
from app.main import app
from app.models.enums import MasteryState, Role, SessionStatus, Verdict
from app.models.schemas.session import SessionResult
from app.models.session import Evaluation, SessionTurn, TeachingSession
from app.models.users import ClassSection, Course, Enrollment, Lecturer, Student, User
from app.realtime.bus import InMemoryEventBus
from app.services.mastery import MasteryService
from app.services.skill_tree import seed_dir
from app.services.speech import MemoryAudioStore

DB_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="đặt TEST_DATABASE_URL để chạy trên Postgres thật")

MAT_KHAU = "Whybi@2026"
_HASH = hash_password(MAT_KHAU) if DB_URL else ""  # băm một lần – Argon2 cố ý chậm
CAY_MAU = json.loads((seed_dir() / "tree_ctdl_gt.json").read_text(encoding="utf-8"))
GOC = "n1_bien_bo_nho"  # nút gốc của cây mẫu – SẴN SÀNG ngay khi phát hành
WEBM = b"\x1a\x45\xdf\xa3kt08-fake-audio"  # chỉ cho STT fake, không phải giọng nói thật


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
        self.qtv = self._tao(Role.ADMIN, "Quản trị viên")
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
        for u in (self.gv_a, self.gv_b, self.sv_a, self.sv_b, self.sv_c, self.qtv):
            u.headers = self.dang_nhap(u.email)

    def _tao(self, role: Role, ten: str) -> NguoiDung:
        email = f"kt08.{uuid4().hex[:8]}@whybi.test"
        u = User(id=uuid4(), full_name=ten, email=email, password_hash=_HASH, role=role)
        self.db.add(u)
        self.db.flush()
        if role == Role.LECTURER:
            self.db.add(Lecturer(user_id=u.id))
        elif role == Role.STUDENT:
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

    import app.db.session as db_mod
    import app.services.mastery as mastery_mod

    bus = InMemoryEventBus()
    monkeypatch.setattr(mastery_mod, "get_bus", lambda: bus)
    engine = create_engine(DB_URL)
    conn = engine.connect()
    tx = conn.begin()
    db = Session(bind=conn, join_transaction_mode="create_savepoint")

    # WebSocket mở SessionLocal riêng; dùng cùng transaction, giữ nguyên mọi hàm kiểm quyền thật.
    @contextmanager
    def session_local():
        yield db

    monkeypatch.setattr(db_mod, "SessionLocal", session_local)
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as api:
            yield Lop(db, api)
    finally:
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


def test_lich_su_phien_chi_co_phien_cua_minh(lop, cay):
    sid = _qua_nut(lop, lop.sv_a, cay)
    _qua_nut(lop, lop.sv_b, cay)
    r = lop.api.get("/api/v1/me/sessions", headers=lop.sv_a.headers, params={"classId": str(lop.lop1)})
    assert r.status_code == 200
    assert {s["sessionId"] for s in r.json()} == {str(sid)}
    assert all(s["studentId"] == str(lop.sv_a.id) for s in r.json())


# --- NFR-08: dữ liệu CÓ TÊN SV chỉ GV phụ trách lớp xem được -------------------------------------


def test_gv_lop_khac_khong_xem_duoc_ban_do_nhiet_co_ten(lop, cay):
    r = lop.api.get(f"/api/v1/classes/{lop.lop1}/heatmap", headers=lop.gv_b.headers)
    assert r.status_code == 403
    assert lop.sv_a.ten not in r.text


def test_gv_lop_khac_khong_xem_duoc_chi_tiet_nut(lop, cay):
    r = lop.api.get(f"/api/v1/classes/{lop.lop1}/nodes/{cay['nodes'][0]['id']}/detail", headers=lop.gv_b.headers)
    assert r.status_code == 403


def test_gv_lop_khac_khong_xem_duoc_ho_so_sv(lop, cay):
    r = lop.api.get(f"/api/v1/classes/{lop.lop1}/students/{lop.sv_a.id}/profile", headers=lop.gv_b.headers)
    assert r.status_code == 403
    assert lop.sv_a.ten not in r.text


def test_gv_khong_xem_duoc_ho_so_sv_khong_thuoc_lop_minh(lop, cay):
    """GV A hỏi hồ sơ SV C (không thuộc lớp 1) qua lớp của mình ⇒ không được trả tên / kết quả."""
    ok = lop.api.get(f"/api/v1/classes/{lop.lop1}/students/{lop.sv_a.id}/profile", headers=lop.gv_a.headers)
    assert ok.status_code == 200 and lop.sv_a.ten in ok.text
    r = lop.api.get(f"/api/v1/classes/{lop.lop1}/students/{lop.sv_c.id}/profile", headers=lop.gv_a.headers)
    # 404 hợp lệ khi quan hệ SV–lớp không tồn tại; request trên chứng minh route hoạt động.
    assert r.status_code in (403, 404)
    assert lop.sv_c.ten not in r.text


def test_gv_lop_khac_khong_xuat_duoc_bao_cao(lop, cay):
    r = lop.api.get(f"/api/v1/classes/{lop.lop1}/report", headers=lop.gv_b.headers, params={"format": "csv"})
    assert r.status_code == 403


def test_gv_phu_trach_xem_duoc_ban_do_nhiet_co_ten(lop, cay):
    r = lop.api.get(f"/api/v1/classes/{lop.lop1}/heatmap", headers=lop.gv_a.headers)
    assert r.status_code == 200 and lop.sv_a.ten in r.text


# --- NFR-09, BR-13: chỉ LƯU ghi âm khi SV đồng ý (hợp đồng C1-12) -------------------------------


class KhoAmThanh(MemoryAudioStore):
    """Kho dùng chung cho SpeechService (ghi + metadata) và SessionHistoryService (đọc / xóa)."""

    def get(self, url: str) -> bytes:
        return self.objects[urlparse(url).path.lstrip("/")]["data"]

    def remove(self, url: str) -> None:
        self.objects.pop(urlparse(url).path.lstrip("/"), None)


@pytest.fixture
def kho_am_thanh(monkeypatch):
    import app.services.session_history as history
    import app.services.speech as speech

    store = KhoAmThanh()
    monkeypatch.setattr(speech, "get_audio_store", lambda: store)
    monkeypatch.setattr(history, "default_storage", lambda: store)
    return store


def _mo_phien_giong(lop, cay) -> str:
    node = next(n for n in cay["nodes"] if n["key"] == GOC)
    r = lop.api.post("/api/v1/sessions", headers=lop.sv_a.headers, json={"nodeId": node["id"], "inputMode": "VOICE"})
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "EXPLAINING"
    return r.json()["sessionId"]


def _tai_am_thanh(lop, sid, consent="true", nguoi=None):
    return lop.api.post(
        f"/api/v1/sessions/{sid}/audio",
        headers=(nguoi or lop.sv_a).headers,
        files={"file": ("loi-giang.webm", WEBM, "audio/webm")},
        data={} if consent is None else {"consent": consent},
    )


def _gui_luot_giong(lop, sid, transcript) -> SessionTurn:
    r = lop.api.post(
        f"/api/v1/sessions/{sid}/turns",
        headers=lop.sv_a.headers,
        json={
            "text": transcript["text"],
            "inputMode": "VOICE",
            "audioRef": transcript["audioRef"],
            "sttConfidence": transcript["confidence"],
        },
    )
    assert r.status_code == 200, r.text
    return lop.db.scalars(
        select(SessionTurn).where(SessionTurn.session_id == UUID(sid), SessionTurn.speaker == "STUDENT")
    ).one()


@pytest.mark.parametrize("consent", [None, "false"], ids=["khong-gui", "tu-choi"])
def test_khong_dong_y_van_chep_chu_nhung_khong_luu_hay_nghe_lai(lop, cay, kho_am_thanh, consent):
    sid = _mo_phien_giong(lop, cay)
    r = _tai_am_thanh(lop, sid, consent)
    assert r.status_code == 200, r.text
    transcript = r.json()
    assert transcript["text"] and transcript["audioRef"].startswith("unsaved:")
    turn = _gui_luot_giong(lop, sid, transcript)
    assert kho_am_thanh.objects == {}
    for nguoi in (lop.sv_a, lop.gv_a):
        audio = lop.api.get(f"/api/v1/turns/{turn.id}/audio", headers=nguoi.headers)
        assert audio.status_code == 404 and _ma(audio) == "AUDIO_NOT_AVAILABLE"
    history = lop.api.get(f"/api/v1/me/sessions/{sid}", headers=lop.sv_a.headers)
    assert history.status_code == 200
    assert all(t["audioUrl"] is None for t in history.json()["turns"])


def test_dong_y_luu_ghi_am_va_chi_chu_phien_gv_phu_trach_nghe_duoc(lop, cay, kho_am_thanh):
    sid = _mo_phien_giong(lop, cay)
    r = _tai_am_thanh(lop, sid)
    assert r.status_code == 200, r.text
    transcript = r.json()
    key = transcript["audioRef"].removeprefix("s3://")
    assert key.startswith(f"audio/{sid}/") and key.endswith(".webm")
    assert kho_am_thanh.objects[key] == {
        "data": WEBM,
        "content_type": "audio/webm",
        "metadata": {"consent": "true", "session-id": sid, "retention-days": "30"},
    }
    turn = _gui_luot_giong(lop, sid, transcript)
    url = f"/api/v1/turns/{turn.id}/audio"
    for nguoi in (lop.sv_a, lop.gv_a):
        audio = lop.api.get(url, headers=nguoi.headers)
        assert audio.status_code == 200 and audio.content == WEBM
        assert audio.headers["content-type"] == "audio/webm"
    for nguoi in (lop.sv_b, lop.sv_c, lop.gv_b, lop.qtv):
        audio = lop.api.get(url, headers=nguoi.headers)
        assert audio.status_code == 403 and _ma(audio) == "FORBIDDEN"
        assert WEBM not in audio.content


def test_dong_y_khong_truyen_sang_lan_tai_ke_tiep(lop, cay, kho_am_thanh):
    sid = _mo_phien_giong(lop, cay)
    accepted = _tai_am_thanh(lop, sid)
    assert accepted.status_code == 200, accepted.text
    saved = dict(kho_am_thanh.objects)
    for consent in (None, "false"):
        r = _tai_am_thanh(lop, sid, consent)
        assert r.status_code == 200 and r.json()["audioRef"].startswith("unsaved:")
        assert kho_am_thanh.objects == saved


@pytest.mark.parametrize("days", [30, 7])
def test_het_han_luu_xoa_am_thanh_giu_transcript(lop, cay, kho_am_thanh, monkeypatch, days):
    from app.services.session_history import purge_expired_audio

    monkeypatch.setattr(get_settings(), "audio_retention_days", days)
    sid = _mo_phien_giong(lop, cay)
    r = _tai_am_thanh(lop, sid)
    assert r.status_code == 200, r.text
    turn = _gui_luot_giong(lop, sid, r.json())
    content = turn.content
    key = r.json()["audioRef"].removeprefix("s3://")
    assert kho_am_thanh.objects[key]["metadata"]["retention-days"] == str(days)
    cutoff = turn.created_at + timedelta(days=days)
    assert purge_expired_audio(lop.db, now=cutoff - timedelta(seconds=1)) == 0
    assert lop.api.get(f"/api/v1/turns/{turn.id}/audio", headers=lop.sv_a.headers).status_code == 200
    assert purge_expired_audio(lop.db, now=cutoff + timedelta(seconds=1)) == 1
    assert key not in kho_am_thanh.objects
    lop.db.refresh(turn)
    assert turn.content == content and turn.audio_url is None
    for nguoi in (lop.sv_a, lop.gv_a):
        audio = lop.api.get(f"/api/v1/turns/{turn.id}/audio", headers=nguoi.headers)
        assert audio.status_code == 404 and _ma(audio) == "AUDIO_NOT_AVAILABLE"


def test_khong_tai_ghi_am_vao_phien_cua_sv_khac(lop, cay, kho_am_thanh):
    sid = _mo_phien_giong(lop, cay)
    r = _tai_am_thanh(lop, sid, nguoi=lop.sv_b)
    assert r.status_code == 403 and _ma(r) == "FORBIDDEN"
    assert kho_am_thanh.objects == {}


@pytest.mark.parametrize("path", ["sessions/{sid}", "me/sessions/{sid}"])
def test_khoi_phuc_va_lich_su_chi_chu_phien_xem_duoc(lop, cay, kho_am_thanh, path):
    sid = _mo_phien_giong(lop, cay)
    upload = _tai_am_thanh(lop, sid)
    assert upload.status_code == 200, upload.text
    turn = _gui_luot_giong(lop, sid, upload.json())
    url = "/api/v1/" + path.format(sid=sid)
    own = lop.api.get(url, headers=lop.sv_a.headers)
    assert own.status_code == 200 and turn.content in own.text
    for nguoi in (lop.sv_b, lop.sv_c, lop.gv_a, lop.gv_b, lop.qtv):
        denied = lop.api.get(url, headers=nguoi.headers)
        assert denied.status_code == 403 and _ma(denied) == "FORBIDDEN"
        assert turn.content not in denied.text and "s3://" not in denied.text


@pytest.mark.parametrize("kenh", ["heatmap", "session"])
def test_websocket_chi_chu_lop_hoac_chu_phien_nhan_du_lieu(lop, cay, kenh):
    from app.realtime import gateway

    sid = _mo_phien_giong(lop, cay)
    channel = f"class:{lop.lop1}:heatmap" if kenh == "heatmap" else f"session:{sid}"
    owner = lop.gv_a if kenh == "heatmap" else lop.sv_a
    for nguoi in (lop.gv_a, lop.gv_b, lop.sv_a, lop.sv_b, lop.sv_c, lop.qtv):
        with lop.api.websocket_connect("/api/v1/ws") as ws:
            ws.send_json({"action": "subscribe", "channel": channel, "token": nguoi.headers["Authorization"][7:]})
            reply = ws.receive_json()
            if nguoi is owner:
                assert reply == {"channel": channel, "event": "subscribed", "payload": {}}
                gateway.broadcast(channel, "kt08.private", {"fullName": lop.sv_a.ten})
                assert ws.receive_json()["payload"] == {"fullName": lop.sv_a.ten}
                ws.send_json({"action": "unsubscribe", "channel": channel})
                assert ws.receive_json()["event"] == "unsubscribed"
            else:
                assert reply["event"] == "error"
                assert reply["payload"]["code"] in {"FORBIDDEN", "NOT_CLASS_OWNER"}
                assert lop.sv_a.ten not in json.dumps(reply, ensure_ascii=False)
                assert gateway.hub.listeners(channel) == 0
                gateway.broadcast(channel, "kt08.private", {"fullName": lop.sv_a.ten})
                ws.send_json({"action": "ping"})
                assert ws.receive_json()["event"] == "pong"
