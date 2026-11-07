"""C2-17 – Xong khi: ghi âm quá hạn bị xóa (NFR-09, BR-13). Task dọn: xóa đối tượng, xóa audio_url, giữ transcript."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.core.config import get_settings
from app.models.session import SessionTurn
from app.services.session_history import purge_expired_audio
from app.services.storage import default_storage
from tests.unit import test_rootcause_db as _c212
from tests.unit.test_heatmap_db import hoc
from tests.unit.test_tree_edit_db import DB_URL

world = _c212.world
lop30 = _c212.lop30
N1 = _c212.N1

pytestmark = pytest.mark.skipif(not DB_URL, reason="đặt TEST_DATABASE_URL để chạy trên Postgres thật")


def _turn(w, sess, no, age_days, audio_url):
    t = SessionTurn(
        session_id=sess.id,
        turn_no=no,
        speaker="STUDENT",
        turn_type="EXPLANATION",
        content=f"lượt {no}",
        input_mode="VOICE",
        audio_url=audio_url,
    )
    w.db.add(t)
    w.db.flush()
    t.created_at = datetime.now(UTC) - timedelta(days=age_days)
    w.db.flush()
    return t


def test_don_ghi_am_qua_han(lop30):
    from app.models.session import TeachingSession

    w, svc, sv, ids, _ = lop30
    hoc(w, svc, w.sv, ids[N1], passed=True)
    sess = w.db.query(TeachingSession).filter_by(student_id=w.sv).one()
    days = get_settings().audio_retention_days
    store = default_storage()
    keys = [f"audio/{sess.id}/{uuid4()}.webm" for _ in range(2)]
    for k in keys:
        store.put(k, b"x", "audio/webm")
    old = _turn(w, sess, 1, days + 1, f"s3://{keys[0]}")
    fresh = _turn(w, sess, 2, days - 1, f"s3://{keys[1]}")
    unsaved = _turn(w, sess, 3, days + 5, f"unsaved:{uuid4()}")

    assert purge_expired_audio(w.db) == 1
    w.db.refresh(old), w.db.refresh(fresh), w.db.refresh(unsaved)
    assert old.audio_url is None and old.content == "lượt 1"  # transcript còn
    assert keys[0] not in store.objects and keys[1] in store.objects
    assert fresh.audio_url == f"s3://{keys[1]}" and unsaved.audio_url.startswith("unsaved:")
    assert purge_expired_audio(w.db) == 0  # chạy lại không làm gì


def test_don_ghi_am_khong_xoa_doi_tuong_cua_phien_khac(lop30):
    from app.models.session import TeachingSession

    w, svc, sv, ids, _ = lop30
    hoc(w, svc, w.sv, ids[N1], passed=True)
    sess = w.db.query(TeachingSession).filter_by(student_id=w.sv).one()
    store = default_storage()
    other_key = f"audio/{uuid4()}/{uuid4()}.webm"
    store.put(other_key, b"cua-phien-khac", "audio/webm")
    store.put("syllabi/giao-trinh.pdf", b"%PDF", "application/pdf")
    days = get_settings().audio_retention_days
    t1 = _turn(w, sess, 1, days + 1, f"s3://{other_key}")  # tham chiếu giả tới phiên khác
    t2 = _turn(w, sess, 2, days + 1, f"s3://audio/{sess.id}/../../syllabi/giao-trinh.pdf")
    assert purge_expired_audio(w.db) == 2
    w.db.refresh(t1), w.db.refresh(t2)
    assert t1.audio_url is None and t2.audio_url is None
    assert other_key in store.objects and "syllabi/giao-trinh.pdf" in store.objects
