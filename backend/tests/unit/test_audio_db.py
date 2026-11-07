"""C1-12 – POST /sessions/{id}/audio trên Postgres thật: glossary lấy từ nút của phiên, quyền chủ phiên, phiên đã
kết thúc ⇒ 409. Cần TEST_DATABASE_URL (dùng lại World / cây mẫu của C1-07, C2-09)."""

from uuid import uuid4

import pytest

from app.models.enums import SessionStatus
from app.models.session import TeachingSession
from tests.unit import test_session_orchestrator_db as _c107
from tests.unit.test_session_orchestrator_db import DB_URL, start

# fixture dùng lại của C1-07 (gán, không import tên, để pytest thấy trong mô-đun này)
world, bus, completed, published = _c107.world, _c107.bus, _c107.completed, _c107.published

pytestmark = pytest.mark.skipif(not DB_URL, reason="đặt TEST_DATABASE_URL để chạy trên Postgres thật")

WEBM = b"\x1a\x45\xdf\xa3" + b"\0" * 64


def _audio(w, sid):
    return w.api.post(f"/api/v1/sessions/{sid}/audio", files={"file": ("a.webm", WEBM, "audio/webm")})


def test_owner_gets_transcript_without_storing(published):
    w, tree = published
    sid = start(w, tree).json()["sessionId"]
    r = _audio(w, sid)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["audioRef"].startswith("unsaved:") and body["words"]


def test_other_student_unknown_and_finished_session(published):
    w, tree = published
    sid = start(w, tree).json()["sessionId"]
    w.current = w.sv_out
    assert _audio(w, sid).json()["error"]["code"] == "FORBIDDEN"
    w.current = w.sv
    assert _audio(w, uuid4()).json()["error"]["code"] == "SESSION_NOT_FOUND"
    s = w.db.get(TeachingSession, sid)
    s.status = SessionStatus.ABANDONED
    w.db.commit()
    r = _audio(w, sid)
    assert r.status_code == 409 and r.json()["error"]["code"] == "SESSION_NOT_ACTIVE"
