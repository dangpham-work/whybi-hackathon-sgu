"""C2-17 – Hồ sơ năng lực SV, transcript, ghi âm (FR-HM-07). Nghe lại ghi âm: GV phụ trách lớp hoặc chính SV."""

from uuid import uuid4

import pytest

from app.models.session import SessionTurn, TeachingSession
from app.services.storage import default_storage
from tests.unit import test_rootcause_db as _c212
from tests.unit.test_heatmap_db import hoc
from tests.unit.test_tree_edit_db import DB_URL

world = _c212.world
lop30 = _c212.lop30
N1 = _c212.N1

pytestmark = pytest.mark.skipif(not DB_URL, reason="đặt TEST_DATABASE_URL để chạy trên Postgres thật")


@pytest.fixture
def co_phien(lop30):
    """SV `w.sv` học N1 (Đạt) với 2 lượt: một lượt giọng nói có ghi âm, một lượt gõ."""
    w, svc, sv, ids, _ = lop30
    hoc(w, svc, w.sv, ids[N1], passed=True)
    sess = w.db.query(TeachingSession).filter_by(student_id=w.sv, node_id=ids[N1]).one()
    key = f"audio/{sess.id}/{uuid4()}.webm"
    audio = b"RIFF-fake-audio"
    default_storage().put(key, audio, "audio/webm")
    voice = SessionTurn(
        session_id=sess.id,
        turn_no=1,
        speaker="STUDENT",
        turn_type="EXPLANATION",
        content="Biến là ô nhớ",
        input_mode="VOICE",
        audio_url=f"s3://{key}",
    )
    typed = SessionTurn(
        session_id=sess.id,
        turn_no=2,
        speaker="TUTEE",
        turn_type="QUESTION",
        content="Còn kiểu dữ liệu?",
        input_mode="TEXT",
    )
    w.db.add_all([voice, typed])
    w.db.flush()
    return w, sess, voice, typed, audio


def url(w, suffix=""):
    return f"/api/v1/classes/{w.class_id}/students/{w.sv}/profile{suffix}"


def test_ho_so_co_tien_do_phien_va_transcript(co_phien):
    w, sess, voice, typed, _ = co_phien
    r = w.api.get(url(w))
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["studentId"] == str(w.sv) and p["fullName"] and p["studentCode"]
    assert p["masteredCount"] == 1 and p["totalCount"] == 11
    assert next(n for n in p["progress"] if n["nodeKey"] == N1)["state"] == "MASTERED"
    [s] = p["sessions"]
    assert s["sessionId"] == str(sess.id) and s["nodeKey"] == N1 and s["nodeTitle"]
    assert s["status"] == "COMPLETED" and s["result"]["verdict"] == "PASSED" or s["result"] is None
    t = {x["turnNo"]: x for x in s["turns"]}
    assert t[1]["content"] == "Biến là ô nhớ" and t[1]["audioUrl"] == f"/api/v1/turns/{voice.id}/audio"
    assert t[2]["audioUrl"] is None and t[2]["speaker"] == "TUTEE"


def test_ho_so_sv_ngoai_lop_403(lop30):
    w, *_ = lop30
    w.sv_out_profile = w.sv_out
    r = w.api.get(f"/api/v1/classes/{w.class_id}/students/{w.sv_out}/profile")
    assert r.status_code == 403 and r.json()["error"]["code"] == "NOT_ENROLLED"


@pytest.mark.parametrize("who", ["gv_other", "sv"])
def test_ho_so_chi_gv_phu_trach(co_phien, who):
    w, *_ = co_phien
    w.current = getattr(w, who)
    assert w.api.get(url(w)).status_code == 403


def test_nghe_lai_ghi_am_gv_va_sv_chu_phien(co_phien):
    w, _, voice, typed, audio = co_phien
    a = f"/api/v1/turns/{voice.id}/audio"
    for who in (w.gv, w.sv):
        w.current = who
        r = w.api.get(a)
        assert r.status_code == 200 and r.content == audio and r.headers["content-type"].startswith("audio/")


def test_nghe_lai_nguoi_khac_403_va_khong_co_ghi_am_404(co_phien):
    w, _, voice, typed, _ = co_phien
    w.current = w.gv_other
    assert w.api.get(f"/api/v1/turns/{voice.id}/audio").status_code == 403
    w.current = w.sv_out
    assert w.api.get(f"/api/v1/turns/{voice.id}/audio").status_code == 403
    w.current = w.gv
    r = w.api.get(f"/api/v1/turns/{typed.id}/audio")
    assert r.status_code == 404 and r.json()["error"]["code"] == "AUDIO_NOT_AVAILABLE"
    assert w.api.get(f"/api/v1/turns/{uuid4()}/audio").status_code == 404


@pytest.mark.parametrize("forged", ["other_session", "traversal", "other_bucket_key"])
def test_tham_chieu_ghi_am_gia_khong_doc_duoc(co_phien, forged):
    """audioRef do client gửi: chỉ nhận khóa của chính phiên – không đọc ghi âm phiên khác hay tệp khác trong bucket."""
    w, sess, voice, typed, _ = co_phien
    secret_key = f"audio/{uuid4()}/{uuid4()}.webm"
    default_storage().put(secret_key, b"secret-of-another-session", "audio/webm")
    default_storage().put("syllabi/giao-trinh.pdf", b"%PDF-secret", "application/pdf")
    typed.audio_url = {
        "other_session": f"s3://{secret_key}",
        "traversal": f"s3://audio/{sess.id}/../../syllabi/giao-trinh.pdf",
        "other_bucket_key": "s3://syllabi/giao-trinh.pdf",
    }[forged]
    w.db.flush()
    r = w.api.get(f"/api/v1/turns/{typed.id}/audio")
    assert r.status_code == 404 and r.json()["error"]["code"] == "AUDIO_NOT_AVAILABLE"
    profile = w.api.get(url(w)).json()
    assert next(t for t in profile["sessions"][0]["turns"] if t["turnNo"] == 2)["audioUrl"] is None
