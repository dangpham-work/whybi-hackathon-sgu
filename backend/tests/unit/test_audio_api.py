"""C1-12 – POST /sessions/{id}/audio: multipart file + consent → Transcript (camelCase), lỗi theo AppError."""

from uuid import uuid4

import pytest

from app.ai.providers.stt import FakeSTTProvider
from app.api.deps import CurrentUser, get_current_user
from app.api.sessions import get_orchestrator, get_speech_service
from app.core.errors import AppError
from app.main import app
from app.models.enums import Role
from app.models.schemas.tree import KeyPointSchema, Node, Rubric
from app.services.speech import MemoryAudioStore, SpeechService

WEBM = b"\x1a\x45\xdf\xa3" + b"\0" * 64
NODE = Node(
    key="con_tro",
    title="Con trỏ",
    rubric=Rubric(key_points=[KeyPointSchema(id="KP1", content="Con trỏ lưu địa chỉ của biến khác")]),
)
STUDENT_ID = uuid4()


class FakeOrch:
    def __init__(self) -> None:
        self.error: AppError | None = None
        self.calls: list[tuple] = []

    def audio_node(self, student_id, session_id):
        self.calls.append((student_id, session_id))
        if self.error:
            raise self.error
        return NODE

    def reserve_audio(self, student_id, session_id, audio, ext):  # C2-18: tính hạn mức phút ghi âm trước STT
        pass


@pytest.fixture
def wired():
    store = MemoryAudioStore()
    orch = FakeOrch()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=STUDENT_ID, role=Role.STUDENT)
    app.dependency_overrides[get_orchestrator] = lambda: orch
    app.dependency_overrides[get_speech_service] = lambda: SpeechService(
        stt=FakeSTTProvider(), store=store, min_confidence=0.8
    )
    yield store, orch
    for dep in (get_current_user, get_orchestrator, get_speech_service):
        app.dependency_overrides.pop(dep, None)


def _post(client, sid, data=WEBM, consent=None, name="rec.webm", ctype="audio/webm"):
    form = {} if consent is None else {"consent": "true" if consent else "false"}
    return client.post(f"/api/v1/sessions/{sid}/audio", files={"file": (name, data, ctype)}, data=form)


def test_transcript_normalized_and_low_words_flagged(client, wired):
    store, orch = wired
    sid = uuid4()
    r = _post(client, sid)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["text"].startswith("Con trỏ là biến")  # fake chép "Con chỏ" → chuẩn hóa theo nút
    assert body["lowConfidenceWords"] == ["trỏ"]
    assert body["confidence"] > 0.8 and body["needsConfirmation"] is False
    assert {"word", "confidence"} <= set(body["words"][0])
    assert body["audioRef"].startswith("unsaved:")  # mặc định không đồng ý ⇒ không lưu
    assert store.objects == {}
    assert orch.calls == [(STUDENT_ID, sid)]


def test_consent_stores_recording(client, wired):
    store, _ = wired
    sid = uuid4()
    r = _post(client, sid, consent=True)
    assert r.status_code == 200, r.text
    assert r.json()["audioRef"].startswith(f"s3://audio/{sid}/")
    assert len(store.objects) == 1


@pytest.mark.parametrize("name", ["../../evil.php", r"..\..\evil.exe", "recording.mp3"])
def test_storage_key_and_mime_come_from_audio_not_untrusted_filename(client, wired, name):
    store, _ = wired
    sid = uuid4()
    r = _post(client, sid, consent=True, name=name, ctype="application/x-php")
    assert r.status_code == 200, r.text
    key = r.json()["audioRef"].removeprefix("s3://")
    assert key.startswith(f"audio/{sid}/") and key.endswith(".webm")
    assert len(key.split("/")) == 3 and ".." not in key
    assert store.objects[key]["content_type"] == "audio/webm"


def test_rejects_disguised_file(client, wired):
    r = _post(client, uuid4(), data=b"MZ\x90\x00 not audio", name="x.webm")
    assert r.status_code == 415
    assert r.json()["error"]["code"] == "UNSUPPORTED_AUDIO_FORMAT"


def test_missing_file_is_validation_error(client, wired):
    r = client.post(f"/api/v1/sessions/{uuid4()}/audio", data={"consent": "true"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize(
    "err",
    [
        AppError(404, "SESSION_NOT_FOUND", "x"),
        AppError(403, "FORBIDDEN", "x"),
        AppError(409, "SESSION_NOT_ACTIVE", "x", {"status": "COMPLETED"}),
    ],
)
def test_session_errors_propagate(client, wired, err):
    store, orch = wired
    orch.error = err
    r = _post(client, uuid4())
    assert r.status_code == err.status
    assert r.json()["error"]["code"] == err.code
    assert store.objects == {}


def test_lecturer_cannot_upload(client):
    r = client.post(
        f"/api/v1/sessions/{uuid4()}/audio",
        files={"file": ("a.webm", WEBM, "audio/webm")},
        headers={"Authorization": "Bearer dev-lecturer"},
    )
    assert r.status_code == 403
