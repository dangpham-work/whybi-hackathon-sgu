"""C1-12 – SpeechService: kiểm định dạng / kích thước, chuẩn hóa thuật ngữ theo nút, độ tin cậy từng từ,
lưu ghi âm chỉ khi có cờ đồng ý (BR-13), thời gian xử lý (Xong khi: 60 giây chép xong ≤ 4 giây p95)."""

import struct
import time
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.ai.providers.base import TranscriptResult, TransientProviderError
from app.ai.providers.stt import FakeSTTProvider
from app.core.errors import AppError
from app.models.schemas.session import Transcript
from app.models.schemas.tree import KeyPointSchema, MisconceptionSchema, Node, Rubric
from app.services.speech import (
    MAX_AUDIO_BYTES,
    MemoryAudioStore,
    MinioAudioStore,
    SpeechService,
    build_glossary,
    sniff_audio,
)

NODE = Node(
    id=uuid4(),
    key="con_tro",
    title="Con trỏ",
    description="Con trỏ và cấp phát động với malloc() và free()",
    rubric=Rubric(
        key_points=[
            KeyPointSchema(id="KP1", content="Con trỏ lưu địa chỉ ô nhớ của biến khác"),
            KeyPointSchema(id="KP2", content="Gọi free() để giải phóng vùng nhớ cấp phát động"),
        ],
        misconceptions=[MisconceptionSchema(id="MC1", content="Con trỏ NULL vẫn trỏ tới ô nhớ hợp lệ")],
    ),
)


def wav(seconds: float, rate: int = 16_000) -> bytes:
    """WAV PCM mono 16-bit (đủ header để đọc thời lượng)."""
    n = int(seconds * rate) * 2
    header = b"RIFF" + struct.pack("<I", 36 + n) + b"WAVE"
    fmt = b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
    return header + fmt + b"data" + struct.pack("<I", n) + b"\0" * n


WEBM = b"\x1a\x45\xdf\xa3" + b"\0" * 100


class ScriptedSTT:
    name = "scripted"

    def __init__(self, words: list[tuple[str, float]] | None = None, *, fail: Exception | None = None):
        self.words = words or [("xin", 0.9), ("chào", 0.9)]
        self.fail = fail
        self.calls: list[dict] = []

    def transcribe(self, audio, lang="vi", hints=None):
        self.calls.append({"lang": lang, "hints": hints})
        if self.fail:
            raise self.fail
        ws = [{"word": w, "confidence": c} for w, c in self.words]
        return TranscriptResult(
            text=" ".join(w for w, _ in self.words),
            confidence=sum(c for _, c in self.words) / len(self.words),
            words=ws,
        )


def svc(stt=None, store=None) -> SpeechService:
    return SpeechService(stt=stt or ScriptedSTT(), store=store or MemoryAudioStore(), min_confidence=0.8)


# ------------------------------------------------------------------ định dạng / kích thước


@pytest.mark.parametrize(
    ("data", "ext"),
    [
        (WEBM, "webm"),
        (b"OggS" + b"\0" * 20, "ogg"),
        (wav(0.1), "wav"),
        (b"ID3" + b"\0" * 20, "mp3"),
        (b"\0\0\0\x20ftypM4A " + b"\0" * 20, "m4a"),
    ],
)
def test_sniff_known_formats(data, ext):
    assert sniff_audio(data).ext == ext


def test_rejects_non_audio_even_if_named_audio():
    with pytest.raises(AppError) as e:
        svc().transcribe(b"<?php system($_GET['x']); ?>", NODE, session_id=uuid4(), consent=True)
    assert (e.value.status, e.value.code) == (415, "UNSUPPORTED_AUDIO_FORMAT")


def test_rejects_empty_and_too_large():
    with pytest.raises(AppError) as e:
        svc().transcribe(b"", NODE, session_id=uuid4(), consent=False)
    assert (e.value.status, e.value.code) == (422, "EMPTY_AUDIO")
    with pytest.raises(AppError) as e:
        svc().transcribe(WEBM + b"\0" * MAX_AUDIO_BYTES, NODE, session_id=uuid4(), consent=False)
    assert (e.value.status, e.value.code) == (413, "AUDIO_TOO_LARGE")
    assert e.value.details["maxBytes"] == MAX_AUDIO_BYTES


def test_rejects_wav_longer_than_three_minutes():
    with pytest.raises(AppError) as e:
        svc().transcribe(wav(185, rate=8_000), NODE, session_id=uuid4(), consent=False)
    assert (e.value.status, e.value.code) == (413, "AUDIO_TOO_LONG")


@pytest.mark.parametrize("seconds", [180.1, 182])
@pytest.mark.parametrize("metadata", [False, True])
def test_wav_duration_limit_cannot_be_bypassed(seconds, metadata):
    audio = wav(seconds, rate=8_000)
    if metadata:
        # RIFF cho phép chunk phụ trước fmt; không được bỏ qua kiểm thời lượng.
        chunk = b"JUNK" + struct.pack("<I", 4) + b"meta"
        audio = audio[:4] + struct.pack("<I", len(audio) - 8 + len(chunk)) + audio[8:12] + chunk + audio[12:]
    stt, store = ScriptedSTT(), MemoryAudioStore()
    with pytest.raises(AppError) as err:
        svc(stt, store).transcribe(audio, NODE, session_id=uuid4(), consent=True)
    assert (err.value.status, err.value.code) == (413, "AUDIO_TOO_LONG")
    assert stt.calls == [] and store.objects == {}


def test_accepts_wav_at_exactly_three_minutes():
    assert svc().transcribe(wav(180, rate=8_000), NODE, session_id=uuid4(), consent=False).text


@pytest.mark.parametrize("rewrite_riff_size", [False, True])
def test_rejects_wav_with_short_data_chunk_and_excess_trailing_bytes(rewrite_riff_size):
    audio = wav(1, rate=8_000) + b"\0" * (180 * 8_000 * 2)
    if rewrite_riff_size:
        audio = audio[:4] + struct.pack("<I", len(audio) - 8) + audio[8:]
    stt, store = ScriptedSTT(), MemoryAudioStore()
    with pytest.raises(AppError) as err:
        svc(stt, store).transcribe(audio, NODE, session_id=uuid4(), consent=True)
    assert (err.value.status, err.value.code) == (413, "AUDIO_TOO_LONG")
    assert stt.calls == [] and store.objects == {}


def test_rejects_wav_with_zero_framerate_before_stt_or_storage():
    stt, store = ScriptedSTT(), MemoryAudioStore()
    with pytest.raises(AppError) as err:
        svc(stt, store).transcribe(wav(1, rate=0), NODE, session_id=uuid4(), consent=True)
    assert (err.value.status, err.value.code) == (415, "UNSUPPORTED_AUDIO_FORMAT")
    assert stt.calls == [] and store.objects == {}


def test_rejects_wav_signature_without_valid_audio_header():
    with pytest.raises(AppError) as err:
        svc().transcribe(b"RIFF" + b"\0" * 4 + b"WAVE" + b"\0" * 60, NODE, session_id=uuid4(), consent=False)
    assert (err.value.status, err.value.code) == (415, "UNSUPPORTED_AUDIO_FORMAT")


# ------------------------------------------------------------------ độ tin cậy


def test_low_confidence_words_are_marked():
    t = svc(ScriptedSTT([("con", 0.95), ("trỏ", 0.5), ("là", 0.99)])).transcribe(
        WEBM, NODE, session_id=uuid4(), consent=False
    )
    assert isinstance(t, Transcript)
    assert t.low_confidence_words == ["trỏ"]
    assert t.confidence > 0.8 and t.needs_confirmation is False
    assert [w.word for w in t.words] == ["con", "trỏ", "là"]


def test_high_confidence_needs_no_confirmation():
    t = svc(ScriptedSTT([("con", 0.95), ("trỏ", 0.9)])).transcribe(WEBM, NODE, session_id=uuid4(), consent=False)
    assert t.low_confidence_words == [] and t.needs_confirmation is False


@pytest.mark.parametrize(("conf", "expected"), [(0.64, True), (0.65, False), (0.66, False)])
def test_confirmation_uses_average_threshold_not_individual_words(conf, expected):
    t = svc(ScriptedSTT([("xin", 0.95), ("chào", conf)])).transcribe(WEBM, None, session_id=uuid4(), consent=False)
    assert t.low_confidence_words == ["chào"]
    assert t.needs_confirmation is expected


def test_hints_are_node_terms_and_language_is_vi():
    stt = ScriptedSTT()
    svc(stt).transcribe(WEBM, NODE, session_id=uuid4(), consent=False)
    assert stt.calls[0]["lang"] == "vi"
    hints = stt.calls[0]["hints"]
    assert "Con trỏ" in hints and "free()" in hints and "malloc()" in hints and "NULL" in hints


# ------------------------------------------------------------------ chuẩn hóa thuật ngữ theo nút


def test_normalizes_misheard_node_term():
    t = svc(ScriptedSTT([("con", 0.9), ("chỏ,", 0.6), ("là", 0.9), ("biến", 0.9)])).transcribe(
        WEBM, NODE, session_id=uuid4(), consent=False
    )
    assert t.text == "con trỏ, là biến"
    assert [w.word for w in t.words] == ["con", "trỏ,", "là", "biến"]
    # từ được sửa vẫn giữ độ tin cậy thấp ⇒ vẫn gạch chân để SV xác nhận
    assert t.low_confidence_words == ["trỏ,"]


def test_alias_only_applies_when_term_belongs_to_node():
    words = [("gọi", 0.9), ("phờ", 0.9), ("ri", 0.9), ("nhé", 0.9)]
    t = svc(ScriptedSTT(words)).transcribe(WEBM, NODE, session_id=uuid4(), consent=False)
    assert t.text == "gọi free() nhé"
    other = Node(
        key="vong_lap", title="Vòng lặp for", rubric=Rubric(key_points=[KeyPointSchema(id="KP1", content="x")])
    )
    t2 = svc(ScriptedSTT(words)).transcribe(WEBM, other, session_id=uuid4(), consent=False)
    assert t2.text == "gọi phờ ri nhé"


def test_does_not_touch_unrelated_words():
    words = [("con", 0.9), ("số", 0.9), ("trò", 0.9), ("chơi", 0.9)]
    t = svc(ScriptedSTT(words)).transcribe(WEBM, NODE, session_id=uuid4(), consent=False)
    assert t.text == "con số trò chơi"


@pytest.mark.parametrize("text", ["con trò", "con trở", "con chó", "nu", "nồ", "nun", "mallot()"])
@pytest.mark.parametrize("confidence", [0.4, 0.99])
def test_does_not_correct_student_meaning_or_ambiguous_alias(text, confidence):
    t = svc(ScriptedSTT([(w, confidence) for w in text.split()])).transcribe(
        WEBM, NODE, session_id=uuid4(), consent=False
    )
    assert t.text == text
    assert [w.confidence for w in t.words] == [confidence] * len(text.split())


def test_known_pronunciation_is_not_replaced_across_sentence_boundary():
    t = svc(ScriptedSTT([("con,", 0.9), ("chỏ", 0.6)])).transcribe(WEBM, NODE, session_id=uuid4(), consent=False)
    assert t.text == "con, chỏ"


def test_glossary_from_title_description_rubric():
    g = build_glossary(NODE)
    assert {"con trỏ", "free()", "malloc()", "null"} <= g.terms


def test_node_without_rubric_still_works():
    t = svc().transcribe(WEBM, Node(key="x", title="X"), session_id=uuid4(), consent=False)
    assert t.text == "xin chào"


def test_provider_without_words_splits_text():
    class TextOnly:
        def transcribe(self, audio, lang="vi", hints=None):
            return TranscriptResult(text="con chỏ là", confidence=0.7, words=[])

    t = svc(TextOnly()).transcribe(WEBM, NODE, session_id=uuid4(), consent=False)
    assert t.text == "con trỏ là"
    assert all(w.confidence == pytest.approx(0.7) for w in t.words)
    assert t.needs_confirmation is True


# ------------------------------------------------------------------ lưu ghi âm theo cờ đồng ý (BR-13)


def test_stores_audio_only_with_consent():
    store = MemoryAudioStore()
    sid = uuid4()
    t = svc(store=store).transcribe(WEBM, NODE, session_id=sid, consent=True)
    assert t.audio_ref.startswith(f"s3://audio/{sid}/") and t.audio_ref.endswith(".webm")
    key = t.audio_ref.removeprefix("s3://")
    assert store.objects[key]["data"] == WEBM
    assert store.objects[key]["content_type"] == "audio/webm"
    assert store.objects[key]["metadata"]["consent"] == "true"


def test_no_consent_no_storage():
    store = MemoryAudioStore()
    t = svc(store=store).transcribe(WEBM, NODE, session_id=uuid4(), consent=False)
    assert store.objects == {}
    assert t.audio_ref.startswith("unsaved:")


def test_store_failure_is_reported_not_swallowed():
    class Broken(MemoryAudioStore):
        def put(self, key, data, content_type, metadata):
            raise OSError("minio sập")

    with pytest.raises(AppError) as e:
        svc(store=Broken()).transcribe(WEBM, NODE, session_id=uuid4(), consent=True)
    assert (e.value.status, e.value.code) == (503, "AUDIO_STORE_UNAVAILABLE")


def test_existing_audio_retention_does_not_rewrite_shared_bucket_lifecycle():
    from minio.commonconfig import ENABLED, Filter
    from minio.lifecycleconfig import Expiration, LifecycleConfig, Rule

    from app.core.config import get_settings

    rules = [
        Rule(ENABLED, rule_filter=Filter(prefix="documents/"), rule_id="syllabus", expiration=Expiration(days=90)),
        Rule(
            ENABLED,
            rule_filter=Filter(prefix="audio/"),
            rule_id="audio-retention",
            expiration=Expiration(days=get_settings().audio_retention_days),
        ),
    ]
    client = Mock()
    client.bucket_exists.return_value = True
    client.get_bucket_lifecycle.return_value = LifecycleConfig(rules)
    store = MinioAudioStore()
    store._client = client
    store.put("audio/session/test.webm", WEBM, "audio/webm", {"consent": "true"})
    client.set_bucket_lifecycle.assert_not_called()
    client.put_object.assert_called_once()


def test_retention_update_preserves_other_bucket_rules():
    from minio.commonconfig import ENABLED, Filter
    from minio.lifecycleconfig import Expiration, LifecycleConfig, Rule

    other = Rule(ENABLED, rule_filter=Filter(prefix="documents/"), rule_id="syllabus", expiration=Expiration(days=90))
    client = Mock()
    client.bucket_exists.return_value = True
    client.get_bucket_lifecycle.return_value = LifecycleConfig([other])
    store = MinioAudioStore()
    store._client = client
    store.put("audio/session/test.webm", WEBM, "audio/webm", {"consent": "true"})
    written = client.set_bucket_lifecycle.call_args.args[1].rules
    assert written[0] is other
    assert [r.rule_id for r in written] == ["syllabus", "audio-retention"]


@pytest.mark.parametrize("code", ["BucketAlreadyOwnedByYou", "AccessDenied", "BucketAlreadyExists"])
def test_concurrent_bucket_creation_only_ignores_already_owned_bucket(code):
    from minio.error import S3Error

    client = Mock()
    client.bucket_exists.return_value = False
    client.make_bucket.side_effect = S3Error(
        response=None, code=code, message="test", resource=None, request_id=None, host_id=None
    )
    client.get_bucket_lifecycle.return_value = None
    store = MinioAudioStore()
    store._client = client
    if code == "BucketAlreadyOwnedByYou":
        store.put("audio/session/test.webm", WEBM, "audio/webm", {"consent": "true"})
        client.put_object.assert_called_once()
    else:
        with pytest.raises(S3Error) as err:
            store.put("audio/session/test.webm", WEBM, "audio/webm", {"consent": "true"})
        assert err.value.code == code
        client.put_object.assert_not_called()


# ------------------------------------------------------------------ lỗi STT


def test_transient_stt_error_retried_once_then_succeeds():
    class Flaky(ScriptedSTT):
        def transcribe(self, audio, lang="vi", hints=None):
            if not self.calls:
                self.calls.append({})
                raise TransientProviderError("timeout")
            return super().transcribe(audio, lang, hints)

    assert svc(Flaky()).transcribe(WEBM, NODE, session_id=uuid4(), consent=False).text == "xin chào"


def test_stt_failure_maps_to_app_error():
    with pytest.raises(AppError) as e:
        svc(ScriptedSTT(fail=TransientProviderError("sập"))).transcribe(WEBM, NODE, session_id=uuid4(), consent=False)
    assert (e.value.status, e.value.code) == (503, "STT_UNAVAILABLE")


def test_empty_transcript_is_rejected():
    class Silent:
        def transcribe(self, audio, lang="vi", hints=None):
            return TranscriptResult(text="  ", confidence=0.0, words=[])

    with pytest.raises(AppError) as e:
        svc(Silent()).transcribe(WEBM, NODE, session_id=uuid4(), consent=False)
    assert (e.value.status, e.value.code) == (422, "NO_SPEECH_DETECTED")


# ------------------------------------------------------------------ Xong khi: 60 giây ≤ 4 giây p95 (adapter fake)


def test_sixty_second_recording_p95_under_four_seconds_with_fake_adapter():
    """Đo phần backend (kiểm định dạng, chuẩn hóa, lưu) với adapter fake; độ trễ STT thật đo ở KT-10."""
    audio = wav(60)
    long_words = list(FakeSTTProvider.SAMPLE) * 20  # ~220 từ ≈ 60 giây nói
    s = SpeechService(stt=ScriptedSTT(long_words), store=MemoryAudioStore(), min_confidence=0.8)
    times = []
    for _ in range(20):
        t0 = time.perf_counter()
        s.transcribe(audio, NODE, session_id=uuid4(), consent=True)
        times.append(time.perf_counter() - t0)
    p95 = sorted(times)[int(0.95 * len(times)) - 1]
    assert p95 <= 4.0
