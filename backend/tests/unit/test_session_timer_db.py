"""C1-15 – Xong khi: hết giờ được ghi nhận; đổi số câu / ngưỡng Đạt trong cấu hình lớp thì phiên đổi theo (FR-TB-11,
FR-HM-08). Cần TEST_DATABASE_URL (dùng lại World của C1-07)."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi import Depends

from app.api import sessions as sessions_api
from app.core.config import get_settings
from app.db.session import get_db
from app.main import app
from app.models.session import SessionTurn
from app.models.users import ClassSection
from app.services.session_orchestrator import LATE_NOTICE, TIMEOUT_TEXT, SessionOrchestrator
from tests.unit import test_session_orchestrator_db as _c107
from tests.unit.test_session_orchestrator_db import DB_URL, start, turn

world, bus, completed, published = _c107.world, _c107.bus, _c107.completed, _c107.published

pytestmark = pytest.mark.skipif(not DB_URL, reason="đặt TEST_DATABASE_URL để chạy trên Postgres thật")

LIMIT = get_settings().answer_time_limit_s
GRACE = get_settings().answer_grace_s


class Clock:
    def __init__(self):
        self.t = datetime.now(UTC)

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += timedelta(seconds=seconds)


@pytest.fixture
def played(published):
    """(world, tree, đồng hồ giả) – Orchestrator của API dùng đồng hồ giả để đổi thời điểm nộp bài."""
    c = Clock()
    app.dependency_overrides[sessions_api.get_orchestrator] = lambda db=Depends(get_db): SessionOrchestrator(db, now=c)
    yield (*published, c)
    app.dependency_overrides.pop(sessions_api.get_orchestrator, None)


def _student_turns(w, sid):
    w.db.expire_all()
    return w.db.query(SessionTurn).filter_by(session_id=UUID(sid)).order_by(SessionTurn.turn_no).all()


def test_cau_phan_bien_co_han_con_cau_mo_dau_thi_khong(played):
    w, tree, clock = played
    created = start(w, tree).json()
    assert created["opening"]["deadline"] is None
    reply = turn(w, created["sessionId"], "Lời giảng.", "EXPLANATION").json()
    assert reply["question"]["deadline"] == (clock.t + timedelta(seconds=LIMIT)).isoformat().replace("+00:00", "Z")


def test_tra_loi_trong_han_va_trong_thoi_gian_tre_mang_van_tinh(played):
    w, tree, clock = played
    sid = start(w, tree).json()["sessionId"]
    turn(w, sid, "Lời giảng.", "EXPLANATION")
    clock.advance(LIMIT + GRACE - 1)
    r = turn(w, sid, "Trả lời kịp.").json()
    assert r["notice"] is None
    assert any(t.content == "Trả lời kịp." for t in _student_turns(w, sid))


def test_tra_loi_qua_han_bi_ghi_nhan_het_gio_va_khong_vao_transcript(played):
    w, tree, clock = played
    sid = start(w, tree).json()["sessionId"]
    first = turn(w, sid, "Lời giảng.", "EXPLANATION").json()
    clock.advance(LIMIT + GRACE + 1)
    r = turn(w, sid, "Trả lời trễ.")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["notice"] == LATE_NOTICE
    assert body["questionsAsked"] == first["questionsAsked"] + 1  # sang câu kế (LLM giả hỏi lại cùng chữ)
    rows = _student_turns(w, sid)
    assert "Trả lời trễ." not in [t.content for t in rows]
    miss = [t for t in rows if t.content == TIMEOUT_TEXT]
    assert len(miss) == 1 and miss[0].response_time_ms == LIMIT * 1000
    assert body["question"]["deadline"] is not None  # câu kế có hạn mới


def test_loi_giang_dau_tien_khong_bi_gioi_han_gio(played):
    w, tree, clock = played
    sid = start(w, tree).json()["sessionId"]
    clock.advance(24 * 3600)
    r = turn(w, sid, "Lời giảng rất dài, nộp sau một ngày.", "EXPLANATION").json()
    assert r["notice"] is None and r["status"] == "CHALLENGING"


def test_nut_timeout_ghi_nhan_het_gio_va_sang_cau_ke(played):
    w, tree, _ = played
    sid = start(w, tree).json()["sessionId"]
    first = turn(w, sid, "Lời giảng.", "EXPLANATION").json()
    r = w.api.post(f"/api/v1/sessions/{sid}/timeout").json()
    assert r["questionsAsked"] == first["questionsAsked"] + 1
    assert [t.content for t in _student_turns(w, sid)].count(TIMEOUT_TEXT) == 1


@pytest.mark.parametrize("count", [3, 4, 5])
def test_doi_so_cau_trong_cau_hinh_lop_thi_phien_doi_theo(played, count):
    w, tree, _ = played
    w.db.get(ClassSection, w.class_id).challenge_count = count
    w.db.commit()
    sid = start(w, tree).json()["sessionId"]
    reply = turn(w, sid, "Lời giảng.", "EXPLANATION").json()
    assert reply["questionsTotal"] == count
    while reply["status"] != "COMPLETED":
        reply = turn(w, sid, "Trả lời.").json()
    assert reply["questionsAsked"] == count


def test_doi_cau_hinh_giua_phien_ap_dung_ngay(played):
    w, tree, _ = played
    sid = start(w, tree).json()["sessionId"]
    turn(w, sid, "Lời giảng.", "EXPLANATION")
    w.db.get(ClassSection, w.class_id).challenge_count = 5
    w.db.commit()
    assert turn(w, sid, "Trả lời.").json()["questionsTotal"] == 5


def test_nguong_dat_cua_lop_ap_vao_judge(played, completed):
    w, tree, _ = played
    w.db.get(ClassSection, w.class_id).pass_threshold = 100
    w.db.commit()
    sid = start(w, tree).json()["sessionId"]
    reply = turn(w, sid, "Lời giảng.", "EXPLANATION").json()
    while reply["status"] != "COMPLETED":
        reply = turn(w, sid, "Trả lời.").json()
    assert completed[-1].pass_threshold == 100
    result = w.api.get(f"/api/v1/sessions/{sid}/result").json()
    assert result["passThreshold"] == 100


def test_min_passed_giu_k_cua_rubric_khi_so_cau_trung_khop():
    from app.models.schemas.tree import Rubric

    r = Rubric(key_points=[], min_challenges=3, min_passed_challenges=2)
    k = SessionOrchestrator._min_passed
    assert k(r, 3, 3) == 2 and k(r, 5, 5) == 4 and k(r, 4, 4) == 3
    assert k(r, 5, 2) == 2  # không vượt số câu đã hỏi
