"""C2-20 – Xong khi: SV nghe lại được ghi âm của mình; file CSV và PDF mở đúng số liệu (FR-TB-15, FR-HM-10)."""

import csv
import io
from uuid import uuid4

import pymupdf
import pytest

from app.models.enums import MasteryState, Verdict
from app.models.schemas.session import SessionResult
from app.models.session import Evaluation, SessionTurn, TeachingSession
from app.services.storage import default_storage
from tests.unit import test_rootcause_db as _c212
from tests.unit.test_heatmap_db import hoc
from tests.unit.test_tree_edit_db import DB_URL

world = _c212.world
lop30 = _c212.lop30
vi_du_6_9 = _c212.vi_du_6_9
N1, N6 = _c212.N1, _c212.N6

pytestmark = pytest.mark.skipif(not DB_URL, reason="đặt TEST_DATABASE_URL để chạy trên Postgres thật")

API = "/api/v1"


# --- Lịch sử phiên của SV (FR-TB-15) -------------------------------------------------------------


@pytest.fixture
def lich_su(lop30):
    """w.sv đã học N1 (Đạt) với một lượt giọng nói có ghi âm; sv khác (index 1) cũng học N1."""
    w, svc, sv, ids, _ = lop30
    hoc(w, svc, w.sv, ids[N1], passed=True)
    hoc(w, svc, sv[1], ids[N1], passed=False)
    for sid in (w.sv, sv[1]):  # hoc() chỉ đổi ma trận; dựng nốt phiên đã chấm như Orchestrator lưu
        done = w.db.query(TeachingSession).filter_by(student_id=sid).one()
        done.status = "COMPLETED"
        result = SessionResult(
            session_id=done.id,
            student_id=sid,
            node_id=done.node_id,
            class_id=w.class_id,
            state=MasteryState.MASTERED if sid == w.sv else MasteryState.NOT_PASSED,
            verdict=Verdict.PASSED if sid == w.sv else Verdict.FAILED,
            total_score=80.0 if sid == w.sv else 40.0,
            criteria=[],
        )
        w.db.add(
            Evaluation(
                session_id=done.id,
                total_score=result.total_score,
                verdict=result.verdict.value,
                feedback=result.model_dump_json(by_alias=True),
            )
        )
    w.db.flush()
    sess = w.db.query(TeachingSession).filter_by(student_id=w.sv).one()
    key = f"audio/{sess.id}/{uuid4()}.webm"
    default_storage().put(key, b"ghi-am-cua-toi", "audio/webm")
    turn = SessionTurn(
        session_id=sess.id,
        turn_no=1,
        speaker="STUDENT",
        turn_type="EXPLANATION",
        content="Biến là ô nhớ",
        input_mode="VOICE",
        audio_url=f"s3://{key}",
    )
    w.db.add(turn)
    w.db.flush()
    w.current = w.sv
    return w, sess, turn, sv[1]


def test_lich_su_chi_cua_minh_moi_nhat_truoc(lich_su):
    w, sess, _, other = lich_su
    body = w.api.get(f"{API}/me/sessions").json()
    assert [s["sessionId"] for s in body] == [str(sess.id)]
    assert body[0]["verdict"] == "PASSED" and body[0]["studentId"] == str(w.sv)
    assert w.api.get(f"{API}/me/sessions", params={"class_id": str(w.class_id)}).json() == body
    assert w.api.get(f"{API}/me/sessions", params={"class_id": str(uuid4())}).json() == []
    w.roles[other] = w.roles[w.sv]
    w.current = other
    assert [s["studentId"] for s in w.api.get(f"{API}/me/sessions").json()] == [str(other)]


def test_gv_khong_vao_lich_su_cua_sv(lich_su):
    w, *_ = lich_su
    w.current = w.gv
    assert w.api.get(f"{API}/me/sessions").status_code == 403


def test_chi_tiet_phien_va_nghe_lai_ghi_am_cua_minh(lich_su):
    w, sess, turn, other = lich_su
    d = w.api.get(f"{API}/me/sessions/{sess.id}")
    assert d.status_code == 200, d.text
    body = d.json()
    assert body["sessionId"] == str(sess.id) and body["nodeTitle"] and body["result"]["verdict"] == "PASSED"
    [t] = body["turns"]
    assert t["content"] == "Biến là ô nhớ" and t["audioUrl"] == f"/api/v1/turns/{turn.id}/audio"
    audio = w.api.get(t["audioUrl"])
    assert audio.status_code == 200 and audio.content == b"ghi-am-cua-toi"
    # SV khác không xem được phiên và không nghe được ghi âm
    w.roles[other] = w.roles[w.sv]
    w.current = other
    assert w.api.get(f"{API}/me/sessions/{sess.id}").status_code in (403, 404)
    assert w.api.get(t["audioUrl"]).status_code == 403


def test_chi_tiet_phien_khong_ton_tai_404(lich_su):
    w, *_ = lich_su
    r = w.api.get(f"{API}/me/sessions/{uuid4()}")
    assert r.status_code == 404 and r.json()["error"]["code"] == "SESSION_NOT_FOUND"


# --- Báo cáo lớp (FR-HM-10) ----------------------------------------------------------------------


def report(w, fmt="csv"):
    return w.api.get(f"{API}/classes/{w.class_id}/report", params={"format": fmt})


def test_bao_cao_csv_dung_so_lieu(vi_du_6_9):
    w, ids, truot = vi_du_6_9
    r = report(w)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv") and "attachment" in r.headers["content-disposition"]
    assert r.content.startswith(b"\xef\xbb\xbf"), "BOM để Excel đọc đúng tiếng Việt"
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    head = rows[0]
    assert head[:4] == ["MSSV", "Họ tên", "Số nút Đạt", "Tiến độ (%)"]
    n6 = head.index("N6")
    students = [x for x in rows[1:] if x and x[0] and not x[0].startswith("Tổng")]
    assert len(students) == 30
    # 12 SV học tới N6: 3 Đạt, 9 Chưa đạt; 18 SV còn lại chưa có ô ở N6
    states = [x[n6] for x in students]
    assert states.count("Đạt") == 3 and states.count("Chưa đạt") == 9
    foot = {x[1]: x for x in rows if len(x) > 1 and x[1] in ("Đã thử", "Đạt", "Tỉ lệ Đạt (%)")}
    assert foot["Đã thử"][n6] == "12" and foot["Đạt"][n6] == "3" and foot["Tỉ lệ Đạt (%)"][n6] == "25"


def test_bao_cao_csv_chan_cong_thuc_excel(vi_du_6_9):
    w, *_ = vi_du_6_9
    from app.models.users import User

    u = w.db.get(User, w.sv)
    u.full_name = '=HYPERLINK("http://x.test","bấm")'
    w.db.flush()
    text = report(w).content.decode("utf-8-sig")
    assert "\n=HYPERLINK" not in text and ",=HYPERLINK" not in text
    assert "'=HYPERLINK" in text


def test_bao_cao_pdf_mo_duoc_va_co_so_lieu(vi_du_6_9):
    w, *_ = vi_du_6_9
    r = report(w, "pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF") and ".pdf" in r.headers["content-disposition"]
    text = "".join(p.get_text() for p in pymupdf.open("pdf", r.content))
    assert "CTDL&GT – Nhóm 02" in text
    assert "Nên giảng lại N5 Con trỏ" in text
    assert "3/12" in text or "25" in text  # N6: 3 Đạt / 12 đã thử
    assert "SV trong lớp" in text  # tên SV có dấu hiển thị đúng


def test_bao_cao_sai_dinh_dang_va_quyen(vi_du_6_9):
    w, *_ = vi_du_6_9
    assert report(w, "xlsx").status_code == 422
    w.current = w.gv_other
    assert report(w).status_code == 403
    w.current = w.sv
    assert report(w).status_code == 403


def test_bao_cao_lop_chua_phat_hanh_cay_404(world):
    r = report(world)
    assert r.status_code == 404 and r.json()["error"]["code"] == "TREE_NOT_PUBLISHED"
