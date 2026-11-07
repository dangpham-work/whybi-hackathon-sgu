"""C1-14 – Xong khi: bật TTS thì câu hỏi được đọc; tắt thì phiên không bị ảnh hưởng. Cần TEST_DATABASE_URL."""

import pytest

from app.ai.providers.base import TransientProviderError
from app.api import sessions as sessions_api
from app.main import app
from app.services.speech import TtsService
from tests.unit import test_session_orchestrator_db as _c107
from tests.unit.test_session_orchestrator_db import DB_URL, node_id, turn

world, bus, completed, published = _c107.world, _c107.bus, _c107.completed, _c107.published

pytestmark = pytest.mark.skipif(not DB_URL, reason="đặt TEST_DATABASE_URL để chạy trên Postgres thật")


class CountingTTS:
    name = "counting"
    content_type = "audio/mpeg"

    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def synthesize(self, text, voice="vi-VN"):
        self.calls.append(text)
        if self.fail:
            raise TransientProviderError("tts down")
        return b"MP3:" + text.encode()


@pytest.fixture
def tts(published):
    from app.services.storage import InMemoryStorage

    engine = CountingTTS()
    store = InMemoryStorage("whybi")
    app.dependency_overrides[sessions_api.get_tts_service] = lambda: TtsService(engine, store)
    yield engine
    app.dependency_overrides.pop(sessions_api.get_tts_service, None)


def start(w, tree, tts_on):
    return w.api.post(
        "/api/v1/sessions", json={"nodeId": node_id(tree, _c107.ROOT), "inputMode": "TEXT", "ttsEnabled": tts_on}
    ).json()


def test_bat_tts_cau_hoi_co_audio_url_va_doc_duoc(tts, published):
    w, tree = published
    created = start(w, tree, True)
    url = created["opening"]["audioUrl"]
    assert url == f"/api/v1/sessions/{created['sessionId']}/turns/1/tts"
    r = w.api.get(url)
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg"
    assert r.content == b"MP3:" + created["opening"]["text"].encode()
    reply = turn(w, created["sessionId"], "Lời giảng.", "EXPLANATION").json()
    assert reply["question"]["audioUrl"].endswith("/tts") and reply["question"]["audioUrl"] != url
    assert w.api.get(reply["question"]["audioUrl"]).status_code == 200


def test_tong_hop_mot_lan_roi_phat_lai_tu_dem(tts, published):
    w, tree = published
    url = start(w, tree, True)["opening"]["audioUrl"]
    w.api.get(url)
    w.api.get(url)
    assert len(tts.calls) == 1


def test_tat_tts_khong_co_audio_url_va_phien_chay_binh_thuong(tts, published):
    w, tree = published
    created = start(w, tree, False)
    assert created["opening"]["audioUrl"] is None
    reply = turn(w, created["sessionId"], "Lời giảng.", "EXPLANATION").json()
    assert reply["question"]["audioUrl"] is None and reply["status"] == "CHALLENGING"
    r = w.api.get(f"/api/v1/sessions/{created['sessionId']}/turns/1/tts")
    assert r.status_code == 404 and r.json()["error"]["code"] == "TTS_NOT_ENABLED" and tts.calls == []


def test_tts_hong_chi_mat_giong_doc_phien_van_chay(published):
    from app.services.storage import InMemoryStorage

    w, tree = published
    app.dependency_overrides[sessions_api.get_tts_service] = lambda: TtsService(
        CountingTTS(fail=True), InMemoryStorage("w")
    )
    try:
        created = start(w, tree, True)
        r = w.api.get(created["opening"]["audioUrl"])
        assert r.status_code == 503 and r.json()["error"]["code"] == "TTS_UNAVAILABLE"
        assert turn(w, created["sessionId"], "Lời giảng.", "EXPLANATION").status_code == 200
    finally:
        app.dependency_overrides.pop(sessions_api.get_tts_service, None)


def test_phan_quyen_va_luot_khong_hop_le(tts, published):
    w, tree = published
    created = start(w, tree, True)
    sid = created["sessionId"]
    assert w.api.get(f"/api/v1/sessions/{sid}/turns/99/tts").json()["error"]["code"] == "TURN_NOT_FOUND"
    turn(w, sid, "Lời giảng của mình.", "EXPLANATION")
    assert w.api.get(f"/api/v1/sessions/{sid}/turns/2/tts").json()["error"]["code"] == "TURN_NOT_FOUND"  # lượt của SV
    w.current = w.sv_out
    assert w.api.get(f"/api/v1/sessions/{sid}/turns/1/tts").json()["error"]["code"] == "FORBIDDEN"
