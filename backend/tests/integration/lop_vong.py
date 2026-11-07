"""Khung dùng chung cho test vòng 2 / vòng 3 trên Postgres thật (KT-14, KT-15). Chủ: Quyền.

Mở rộng `Lop` của KT-08 (`test_bao_mat_phan_quyen_db.py`): xác thực THẬT (Argon2id + POST /auth/login),
phiên giảng chạy trọn qua HTTP với LLM_MODE=fake, một bus trong bộ nhớ cho cả Orchestrator và MasteryService
(MasteryService nghe `session.completed` như tiến trình mastery_listener), thông báo / email bị ghi lại thay vì gửi.
Mỗi test chạy trong một transaction rollback – không để lại dữ liệu.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import get_db
from app.main import app
from app.models.enums import MasteryState, Role, SessionStatus, Verdict
from app.models.schemas.mastery import TOPIC_SESSION_COMPLETED
from app.models.schemas.session import SessionResult
from app.models.session import Evaluation, TeachingSession
from app.models.users import ClassSection, Enrollment, Student, User
from app.realtime.bus import InMemoryEventBus
from app.services.mastery import MasteryService
from tests.integration.test_bao_mat_phan_quyen_db import _HASH, DB_URL, MAT_KHAU, Lop, NguoiDung

__all__ = ["DB_URL", "MAT_KHAU", "CAY_NHO", "LopVong", "lop_vong"]

API = "/api/v1"

# Cây hai nút giống sv-flow.spec.ts (KT-06): với LLM_MODE=fake lời giảng dưới đây ra 78 điểm, Đạt, không thiếu ý.
_RUBRIC = {
    "keyPoints": [
        {"id": f"KP{i + 1}", "content": c, "isRequired": True}
        for i, c in enumerate(["Con trỏ lưu địa chỉ", "Lấy địa chỉ và giải tham chiếu", "Vòng đời của vùng nhớ"])
    ],
    "sourcePages": [45, 46],
}
CAY_NHO = {
    "nodes": [
        {"key": "pointer", "code": "N5", "title": "Con trỏ", "rubric": _RUBRIC},
        {"key": "allocation", "code": "N6", "title": "Cấp phát động", "rubric": _RUBRIC},
    ],
    "edges": [{"fromKey": "pointer", "toKey": "allocation", "source": "LECTURER"}],
}
LOI_GIANG = "Con trỏ lưu địa chỉ của biến. Toán tử & lấy địa chỉ, còn * truy cập giá trị tại địa chỉ đó."
TRA_LOI = "Con tro luu dia chi. Kieu du lieu quyet dinh cach truy cap vung nho."


class LopVong(Lop):
    """Lớp của KT-08 (GV A phụ trách lớp 1, SV A + SV B đã tham gia, GV B, SV C ngoài lớp, QTV) + tiện ích vòng 2/3."""

    def them_sv(self, ten: str, ma: str | None = None) -> NguoiDung:
        """Tạo tài khoản SV (mật khẩu thật) rồi tham gia lớp 1 bằng mã lớp qua API – đúng luồng SV-01."""
        email = f"kt14.{uuid4().hex[:8]}@whybi.test"
        u = User(id=uuid4(), full_name=ten, email=email, password_hash=_HASH, role=Role.STUDENT)
        self.db.add(u)
        self.db.flush()
        self.db.add(Student(user_id=u.id, student_code=ma or uuid4().hex[:10]))
        self.db.flush()
        sv = NguoiDung(u.id, email, ten)
        sv.headers = self.dang_nhap(email)
        code = self.db.scalar(select(ClassSection.join_code).where(ClassSection.id == self.lop1))
        r = self.api.post(f"{API}/classes/join", headers=sv.headers, json={"joinCode": code})
        assert r.status_code == 200, r.text
        return sv

    def ma_sv(self, sv: NguoiDung) -> str:
        return self.db.scalar(select(Student.student_code).where(Student.user_id == sv.id))

    def ghi_danh(self, sv: NguoiDung) -> UUID:
        return self.db.scalar(
            select(Enrollment.id).where(Enrollment.class_id == self.lop1, Enrollment.student_id == sv.id)
        )

    # ------------------------------------------------------------------ cây

    def phat_hanh(self, cay: dict | None = None) -> dict:
        """GV A nhập cây (mặc định CAY_NHO), duyệt từng rubric của chính nút đó, phát hành."""
        if cay is None:
            cay = CAY_NHO
        h = self.gv_a.headers
        r = self.api.post(f"{API}/classes/{self.lop1}/tree-versions", json=cay, headers=h)
        assert r.status_code == 201, r.text
        tv = r.json()
        rubric_of = {n["key"]: n.get("rubric") for n in cay["nodes"]}
        fallback = next(rb for rb in rubric_of.values() if rb)
        for n in tv["nodes"]:
            rb = rubric_of.get(n["key"]) or fallback
            r = self.api.put(f"{API}/nodes/{n['id']}/rubric", json=rb | {"approved": True}, headers=h)
            assert r.status_code == 200, r.text
        r = self.api.post(f"{API}/tree-versions/{tv['id']}/publish", headers=h)
        assert r.status_code == 200, r.text
        return r.json()

    @staticmethod
    def nut(tree: dict, key: str) -> str:
        return next(n["id"] for n in tree["nodes"] if n["key"] == key)

    # ------------------------------------------------------------------ phiên giảng qua HTTP

    def mo_phien(self, sv: NguoiDung, tree: dict, key: str = "pointer", **extra) -> dict:
        r = self.api.post(f"{API}/sessions", headers=sv.headers, json={"nodeId": self.nut(tree, key), **extra})
        assert r.status_code == 201, r.text
        return r.json()

    def luot(self, sv: NguoiDung, sid: str, text: str, turn_type: str = "ANSWER", **extra):
        return self.api.post(
            f"{API}/sessions/{sid}/turns", headers=sv.headers, json={"turnType": turn_type, "text": text, **extra}
        )

    def giang_tron(self, sv: NguoiDung, tree: dict, key: str = "pointer", **extra) -> tuple[str, dict, int]:
        """Mở phiên, giảng, trả lời mọi câu phản biện tới khi chấm xong. Trả (sessionId, lượt cuối, số câu đã trả lời).
        Phản hồi của lượt giảng (câu phản biện đầu tiên) giữ ở `self.luot_giang` để test đọc `questionsTotal`."""
        sid = self.mo_phien(sv, tree, key, **extra)["sessionId"]
        r = self.luot(sv, sid, LOI_GIANG, "EXPLANATION")
        assert r.status_code == 200, r.text
        reply, answered = r.json(), 0
        self.luot_giang = reply
        while reply["status"] == "CHALLENGING":
            answered += 1
            assert answered <= 6, "vòng phản biện phải dừng"
            r = self.luot(sv, sid, TRA_LOI)
            assert r.status_code == 200, r.text
            reply = r.json()
        assert reply["status"] == "COMPLETED", reply
        return sid, reply, answered

    def ket_qua(self, nguoi: NguoiDung, sid: str) -> dict:
        r = self.api.get(f"{API}/sessions/{sid}/result", headers=nguoi.headers)
        assert r.status_code == 200, r.text
        return r.json()

    # ------------------------------------------------------------------ dựng ma trận không qua LLM

    def dat_nut(
        self,
        sv: NguoiDung | UUID,
        tree: dict,
        key: str,
        passed: bool = True,
        score: float | None = None,
        class_id: UUID | None = None,
    ) -> UUID:
        """Một phiên đã chấm ở nút `key` – ghi ma trận qua MasteryService (đúng luật kiến trúc), lưu Evaluation.
        `class_id` mặc định lớp 1 của KT-08; KT-15 truyền lớp mẫu seed."""
        svc = MasteryService(self.db)
        class_id = class_id or self.lop1
        sv_id = sv if isinstance(sv, UUID) else sv.id
        node_id = UUID(self.nut(tree, key))
        sid = uuid4()
        self.db.add(
            TeachingSession(
                id=sid, student_id=sv_id, node_id=node_id, class_id=class_id, input_mode="TEXT", status="CREATED"
            )
        )
        self.db.flush()
        svc.start_session(sv_id, node_id, sid)
        result = SessionResult(
            session_id=sid,
            student_id=sv_id,
            node_id=node_id,
            class_id=class_id,
            state=MasteryState.MASTERED if passed else MasteryState.NOT_PASSED,
            verdict=Verdict.PASSED if passed else Verdict.FAILED,
            total_score=score if score is not None else (85.0 if passed else 40.0),
            criteria=[],
        )
        svc.apply_result(result)
        s = self.db.get(TeachingSession, sid)
        s.status = SessionStatus.COMPLETED
        self.db.add(
            Evaluation(
                session_id=sid,
                total_score=result.total_score,
                verdict=result.verdict.value,
                feedback=result.model_dump_json(by_alias=True),
            )
        )
        self.db.flush()
        return sid


@contextmanager
def _lop_vong(monkeypatch) -> Iterator[tuple[LopVong, InMemoryEventBus, list]]:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    import app.db.session as db_mod
    import app.services.mastery as mastery_mod
    import app.services.notification as notif_mod
    import app.services.session_orchestrator as orch_mod

    bus = InMemoryEventBus()
    monkeypatch.setattr(mastery_mod, "get_bus", lambda: bus)
    monkeypatch.setattr(orch_mod, "get_bus", lambda: bus)
    sent: list[tuple] = []  # (kênh, sự kiện, payload) đẩy WebSocket và ("email", người nhận, tiêu đề)
    monkeypatch.setattr(notif_mod, "broadcast", lambda ch, ev, payload: sent.append((ch, ev, payload)))
    monkeypatch.setattr(notif_mod, "email_sender", lambda to, subject, body: sent.append(("email", to, subject)))

    engine = create_engine(DB_URL)
    conn = engine.connect()
    tx = conn.begin()
    db = Session(bind=conn, join_transaction_mode="create_savepoint")
    # MasteryService nghe session.completed như tiến trình mastery_listener (dùng chung phiên CSDL của test)
    bus.subscribe(TOPIC_SESSION_COMPLETED, lambda e: MasteryService(db, bus=bus).apply_result(e))

    @contextmanager
    def session_local():
        yield db

    monkeypatch.setattr(db_mod, "SessionLocal", session_local)
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as api:
            yield LopVong(db, api), bus, sent
    finally:
        app.dependency_overrides.clear()
        db.close()
        tx.rollback()
        conn.close()
        engine.dispose()


@pytest.fixture
def lop_vong(monkeypatch) -> Iterator[LopVong]:
    with _lop_vong(monkeypatch) as (lop, bus, sent):
        lop.bus, lop.sent = bus, sent
        yield lop
