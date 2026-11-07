"""KT-10: API âm thanh → xem/sửa bản chép → gửi lượt VOICE trên Postgres thật.

Provider STT/LLM, auth và kho âm thanh giả lập; không chứng minh WER hoặc UI SV-05.
Không tự gửi lượt khi vừa phiên âm; việc xác nhận là thao tác riêng của client.
"""

import io
import wave

import pytest

from app.ai.providers.base import TranscriptResult, TransientProviderError
from app.api.sessions import get_speech_service
from app.main import app
from app.services.speech import MemoryAudioStore, SpeechService
from tests.unit import test_session_orchestrator_db as sessions

world, bus, completed, published = sessions.world, sessions.bus, sessions.completed, sessions.published
pytestmark = pytest.mark.skipif(not sessions.DB_URL, reason="cần TEST_DATABASE_URL tới Postgres riêng đã migrate")


def audio(seconds=1):
    out = io.BytesIO()
    with wave.open(out, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(8000)
        stream.writeframes(b"\0\0" * 8000 * seconds)
    return out.getvalue()


class ControlledSTT:
    name = model = "fake"
    unavailable = False

    def transcribe(self, data, lang="vi", hints=None):
        if self.unavailable:
            raise TransientProviderError("KT-10 fixture offline")
        return TranscriptResult(text="Biến là vùng nhớ có tên.", confidence=0.65, words=[])


@pytest.fixture
def voice(published):
    w, tree = published
    provider, store = ControlledSTT(), MemoryAudioStore()
    service = SpeechService(provider, store)
    app.dependency_overrides[get_speech_service] = lambda: service
    response = w.api.post(
        "/api/v1/sessions",
        json={
            "nodeId": sessions.node_id(tree, sessions.ROOT),
            "inputMode": "VOICE",
        },
    )
    assert response.status_code == 201, response.text
    yield w, response.json()["sessionId"], provider, store
    app.dependency_overrides.pop(get_speech_service, None)


def upload(w, sid, data=None, consent=False):
    return w.api.post(
        f"/api/v1/sessions/{sid}/audio",
        files={"file": ("turn.wav", audio() if data is None else data, "audio/wav")},
        data={"consent": str(consent).lower()},
    )


def state(w, sid):
    response = w.api.get(f"/api/v1/sessions/{sid}")
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("consent", [False, True])
def test_low_confidence_transcript_waits_for_explicit_voice_turn_and_preserves_edit(voice, consent):
    w, sid, _, store = voice
    before = state(w, sid)
    response = upload(w, sid, consent=consent)
    assert response.status_code == 200, response.text
    transcript = response.json()
    assert transcript["needsConfirmation"] is True and transcript["confidence"] == 0.65
    assert transcript["lowConfidenceWords"] and transcript["words"]
    assert state(w, sid) == before  # STT chưa phải là gửi lời giảng.
    assert transcript["audioRef"].startswith("s3://audio/" if consent else "unsaved:")
    assert len(store.objects) == int(consent)
    if consent:
        saved = next(iter(store.objects.values()))
        assert saved["metadata"]["consent"] == "true"
    corrected = "Biến là vùng nhớ có tên, lưu giá trị theo kiểu dữ liệu."
    sent = w.api.post(
        f"/api/v1/sessions/{sid}/turns",
        json={
            "turnType": "EXPLANATION",
            "inputMode": "VOICE",
            "text": corrected,
            "audioRef": transcript["audioRef"],
            "sttConfidence": transcript["confidence"],
            "transcriptEdited": True,
        },
    )
    assert sent.status_code == 200 and sent.json()["status"] == "CHALLENGING", sent.text
    saved_turns = [t for t in state(w, sid)["turns"] if t["speaker"] == "STUDENT"]
    assert len(saved_turns) == 1
    assert saved_turns[0]["text"] == corrected and saved_turns[0]["inputMode"] == "VOICE"


def test_stt_outage_keeps_session_usable_and_allows_retry(voice):
    w, sid, provider, store = voice
    before = state(w, sid)
    provider.unavailable = True
    response = upload(w, sid, consent=True)
    assert response.status_code == 503 and response.json()["error"]["code"] == "STT_UNAVAILABLE"
    assert state(w, sid) == before and store.objects == {}
    provider.unavailable = False
    assert upload(w, sid).status_code == 200
    assert state(w, sid) == before


@pytest.mark.parametrize("data,code", [(b"MZ fake audio", "UNSUPPORTED_AUDIO_FORMAT"), (audio(181), "AUDIO_TOO_LONG")])
def test_invalid_audio_does_not_create_student_turn_or_recording(voice, data, code):
    w, sid, _, store = voice
    before = state(w, sid)
    response = upload(w, sid, data=data, consent=True)
    assert response.status_code in {413, 415} and response.json()["error"]["code"] == code
    assert state(w, sid) == before and store.objects == {}
