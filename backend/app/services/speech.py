"""SpeechService – STT qua adapter, glossary thuật ngữ theo nút, ngưỡng tin cậy STT_MIN_CONFIDENCE = 0,80 (mục 6.4).
Chủ: Đăng (C1-12 STT; C1-14 TTS ở `TtsService` cuối tệp).

Luồng POST /sessions/{id}/audio (FR-TB-05…07):
1. Kiểm tệp (bảo mật upload): không rỗng, ≤ MAX_AUDIO_BYTES, nhận dạng định dạng bằng chữ ký byte (không tin
   tên tệp / Content-Type), WAV thì kiểm thời lượng ≤ 3 phút.
2. Gọi adapter STT (`ai/providers/stt.py`) với ngôn ngữ vi + thuật ngữ của nút làm gợi ý; lỗi tạm thời thử lại 1 lần.
3. Chuẩn hóa bí danh phát âm rõ nghĩa theo nút ("phờ ri" → free(), "con chỏ" → con trỏ).
   Giữ nguyên cụm gần giống và bí danh ngắn đa nghĩa để không sửa hộ kiến thức của SV.
4. Từ có độ tin cậy < ngưỡng ⇒ `lowConfidenceWords`; trung bình < ngưỡng ⇒ `needsConfirmation` (6.4.3).
5. Chỉ lưu ghi âm vào MinIO khi SV đã đồng ý (BR-13); không đồng ý ⇒ không lưu, `audioRef = "unsaved:<uuid>"`.
"""

import io
import logging
import re
import threading
import time
import wave
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urlparse
from uuid import UUID, uuid4

from app.ai.providers.base import ProviderError, STTProvider, TransientProviderError, TTSProvider
from app.ai.providers.stt import get_stt_provider
from app.ai.providers.tts import get_tts_provider
from app.core.config import get_settings
from app.core.errors import AppError
from app.models.schemas.session import Transcript, WordConfidence
from app.models.schemas.tree import Node

log = logging.getLogger(__name__)

MAX_AUDIO_SECONDS = 180  # FR-TB-05: ghi âm ≤ 3 phút
MAX_AUDIO_BYTES = 12 * 1024 * 1024  # webm/opus 3 phút ≈ 3 MB; WAV 16 kHz mono 3 phút ≈ 5,8 MB
AUDIO_PREFIX = "audio/"


# ------------------------------------------------------------------ định dạng tệp


@dataclass(frozen=True)
class AudioFormat:
    ext: str
    content_type: str


def sniff_audio(data: bytes) -> AudioFormat | None:
    """Nhận dạng định dạng bằng chữ ký byte đầu tệp."""
    if data.startswith(b"\x1a\x45\xdf\xa3"):
        return AudioFormat("webm", "audio/webm")
    if data.startswith(b"OggS"):
        return AudioFormat("ogg", "audio/ogg")
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return AudioFormat("wav", "audio/wav")
    if data.startswith(b"ID3") or (len(data) > 1 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0):
        return AudioFormat("mp3", "audio/mpeg")
    if data[4:8] == b"ftyp":
        return AudioFormat("m4a", "audio/mp4")
    return None


def _wav_seconds(data: bytes) -> float:
    """Đọc header RIFF; tính cả byte sau đầu PCM để chunk data ngắn không lách giới hạn."""
    try:
        stream = io.BytesIO(data)
        with wave.open(stream, "rb") as audio:
            if audio.getframerate() <= 0:
                raise wave.Error("invalid framerate")
            # Toàn bộ tệp sẽ được gửi/lưu: bảo thủ tính cả chunk phụ/byte nối sau PCM.
            # Trừ header đã đọc để WAV đúng 180 giây vẫn được chấp nhận.
            payload_frames = (len(data) - stream.tell()) / (audio.getnchannels() * audio.getsampwidth())
            return max(audio.getnframes(), payload_frames) / audio.getframerate()
    except (wave.Error, EOFError) as e:
        raise AppError(415, "UNSUPPORTED_AUDIO_FORMAT", "Tệp WAV không hợp lệ") from e


def validate_audio(data: bytes) -> AudioFormat:
    if not data:
        raise AppError(422, "EMPTY_AUDIO", "Tệp ghi âm rỗng")
    if len(data) > MAX_AUDIO_BYTES:
        raise AppError(413, "AUDIO_TOO_LARGE", "Tệp ghi âm quá lớn", {"maxBytes": MAX_AUDIO_BYTES})
    fmt = sniff_audio(data)
    if fmt is None:
        raise AppError(
            415,
            "UNSUPPORTED_AUDIO_FORMAT",
            "Chỉ nhận ghi âm webm, ogg, wav, mp3, m4a",
            {"allowed": ["webm", "ogg", "wav", "mp3", "m4a"]},
        )
    if fmt.ext == "wav":
        secs = _wav_seconds(data)
        if secs > MAX_AUDIO_SECONDS:
            raise AppError(
                413, "AUDIO_TOO_LONG", "Ghi âm dài quá 3 phút", {"maxSeconds": MAX_AUDIO_SECONDS, "seconds": int(secs)}
            )
    return fmt


# ------------------------------------------------------------------ glossary theo nút

_TOKEN = re.compile(r"\w+(?:\(\))?")
_EDGE_PUNCT = re.compile(r"^(\W*?)(\w.*?(?:\(\))?)(\W*)$", re.S)

# Bí danh phát âm phổ biến → thuật ngữ chuẩn (mục 6.4.2). Chỉ áp khi thuật ngữ chuẩn có trong nút.
BASE_ALIASES: dict[str, str] = {
    "phờ ri": "free()",
    "phri": "free()",
    "ma lóc": "malloc()",
    "ma lốc": "malloc()",
    "con chỏ": "con trỏ",
}


def _is_technical(term: str) -> bool:
    """Thuật ngữ kỹ thuật giữ nguyên dạng viết (free(), NULL, malloc())."""
    return term.isascii() and (term.endswith("()") or (term.isupper() and len(term) >= 2) or "_" in term)


@dataclass
class Glossary:
    terms: set[str] = field(default_factory=set)  # mọi cụm 1–3 từ (chữ thường) xuất hiện trong nút
    display: dict[str, str] = field(default_factory=dict)  # chữ thường → dạng viết gốc
    hints: list[str] = field(default_factory=list)  # gợi ý gửi STT

    def lookup(self, key: str) -> str | None:
        """Chỉ đổi bí danh đã biết; độ giống chuỗi không chứng minh SV nói đúng thuật ngữ."""
        alias = BASE_ALIASES.get(key)
        if alias and alias.lower() in self.terms:
            return self.display.get(alias.lower(), alias)
        return None


def build_glossary(node: Node | None) -> Glossary:
    g = Glossary()
    if node is None:
        return g
    texts = [node.title, node.description or ""]
    if node.rubric:
        texts += [kp.content for kp in node.rubric.key_points]
        texts += node.rubric.optional_points
        texts += [m.content for m in node.rubric.misconceptions]
    for text in texts:
        toks = _TOKEN.findall(text)
        for n in (1, 2, 3):
            for i in range(len(toks) - n + 1):
                phrase = " ".join(toks[i : i + n])
                low = phrase.lower()
                g.terms.add(low)
                g.display.setdefault(low, phrase)
    hints = [node.title] + [g.display[t] for t in sorted(g.terms) if _is_technical(g.display[t])]
    g.hints = list(dict.fromkeys(hints))[:50]
    return g


def _split(word: str) -> tuple[str, str, str]:
    m = _EDGE_PUNCT.match(word.strip())
    return (m.group(1), m.group(2), m.group(3)) if m else ("", word.strip(), "")


def normalize_terms(words: list[WordConfidence], glossary: Glossary) -> list[WordConfidence]:
    """Thay cụm 3/2/1 từ nghe nhầm bằng thuật ngữ của nút. Từ thay thế giữ độ tin cậy thấp nhất của cụm gốc
    (vẫn gạch chân để SV xác nhận); giữ dấu câu hai đầu và chữ hoa đầu cụm."""
    if not glossary.terms:
        return words
    parts = [_split(w.word) for w in words]
    out: list[WordConfidence] = []
    i = 0
    while i < len(words):
        for n in (3, 2, 1):
            if i + n > len(words):
                continue
            span = parts[i : i + n]
            key = " ".join(p[1] for p in span).lower()
            if n > 1 and any(p[2] for p in span[:-1]):  # có dấu câu giữa cụm ⇒ không gộp
                continue
            repl = glossary.lookup(key)
            if repl is None:
                if key in glossary.terms and n > 1:  # cụm đúng sẵn ⇒ giữ, không xét cụm con
                    out.extend(words[i : i + n])
                    i += n
                    break
                continue
            confs = [w.confidence for w in words[i : i + n]]
            rws = [rw if _is_technical(rw) else rw.lower() for rw in repl.split(" ")]
            if len(rws) != n:  # số từ đổi ⇒ mọi từ mới nhận độ tin cậy thấp nhất của cụm
                confs = [min(confs)] * len(rws)
            if span[0][1][:1].isupper() and not _is_technical(rws[0]):
                rws[0] = rws[0][:1].upper() + rws[0][1:]
            rws[0] = span[0][0] + rws[0]
            rws[-1] = rws[-1] + span[-1][2]
            out.extend(WordConfidence(word=rw, confidence=c) for rw, c in zip(rws, confs, strict=True))
            i += n
            break
        else:
            out.append(words[i])
            i += 1
    return out


# ------------------------------------------------------------------ kho ghi âm


class AudioStore(Protocol):
    def put(self, key: str, data: bytes, content_type: str, metadata: dict[str, str]) -> None: ...


class MemoryAudioStore:
    """Kho trong bộ nhớ – dùng cho test."""

    def __init__(self) -> None:
        self.objects: dict[str, dict] = {}

    def put(self, key: str, data: bytes, content_type: str, metadata: dict[str, str]) -> None:
        self.objects[key] = {"data": data, "content_type": content_type, "metadata": metadata}


class MinioAudioStore:
    """MinIO / S3 (S3_ENDPOINT, S3_BUCKET). Lần đầu: tạo bucket nếu thiếu và thêm luật tự xóa `audio/` sau
    AUDIO_RETENTION_DAYS ngày (BR-13) – giữ nguyên các luật lifecycle khác của bucket."""

    RULE_ID = "audio-retention"

    def __init__(self) -> None:
        self._client = None
        self._ready = False
        self._lock = threading.Lock()

    def _get_client(self):
        from minio import Minio

        s = get_settings()
        u = urlparse(s.s3_endpoint)
        return Minio(
            u.netloc or u.path,
            access_key=s.s3_access_key,
            secret_key=s.s3_secret_key,
            secure=u.scheme == "https",
        )

    def _ensure_bucket(self) -> None:
        from minio.commonconfig import ENABLED, Filter
        from minio.error import S3Error
        from minio.lifecycleconfig import Expiration, LifecycleConfig, Rule

        s = get_settings()
        if not self._client.bucket_exists(s.s3_bucket):
            try:
                self._client.make_bucket(s.s3_bucket)
            except S3Error as e:
                if e.code != "BucketAlreadyOwnedByYou":
                    raise
        current = self._client.get_bucket_lifecycle(s.s3_bucket)
        desired = Rule(
            ENABLED,
            rule_filter=Filter(prefix=AUDIO_PREFIX),
            rule_id=self.RULE_ID,
            expiration=Expiration(days=s.audio_retention_days),
        )
        if current and desired in current.rules:
            return  # Không ghi đè ảnh chụp lifecycle cũ khi chính sách audio đã đúng.
        rules = [r for r in (current.rules if current else []) if r.rule_id != self.RULE_ID]
        rules.append(desired)
        self._client.set_bucket_lifecycle(s.s3_bucket, LifecycleConfig(rules))

    def put(self, key: str, data: bytes, content_type: str, metadata: dict[str, str]) -> None:
        with self._lock:
            if self._client is None:
                self._client = self._get_client()
            if not self._ready:
                self._ensure_bucket()
                self._ready = True
        self._client.put_object(
            get_settings().s3_bucket, key, io.BytesIO(data), len(data), content_type=content_type, metadata=metadata
        )


_default_store: MinioAudioStore | None = None


def get_audio_store() -> AudioStore:
    global _default_store
    if _default_store is None:
        _default_store = MinioAudioStore()
    return _default_store


# ------------------------------------------------------------------ service


class SpeechService:
    def __init__(
        self,
        stt: STTProvider | None = None,
        store: AudioStore | None = None,
        *,
        min_confidence: float | None = None,
    ) -> None:
        self.stt = stt or get_stt_provider()
        self.store = store or get_audio_store()
        self.min_confidence = get_settings().stt_min_confidence if min_confidence is None else min_confidence

    def _call_stt(self, audio: bytes, hints: list[str]):
        name = getattr(self.stt, "name", type(self.stt).__name__)
        for attempt in (1, 2):
            try:
                return self.stt.transcribe(audio, "vi", hints)
            except TransientProviderError as e:
                log.warning("stt.retry", extra={"provider": name, "attempt": attempt, "error": str(e)})
                if attempt == 2:
                    raise AppError(
                        503, "STT_UNAVAILABLE", "Dịch vụ nhận dạng giọng nói tạm lỗi", {"provider": name}
                    ) from e
            except ProviderError as e:
                log.error("stt.error", extra={"provider": name, "error": str(e)})
                raise AppError(503, "STT_UNAVAILABLE", "Dịch vụ nhận dạng giọng nói lỗi", {"provider": name}) from e
        raise AssertionError("không tới được")  # pragma: no cover

    def transcribe(self, audio: bytes, node: Node | None, *, session_id: UUID, consent: bool) -> Transcript:
        t0 = time.perf_counter()
        fmt = validate_audio(audio)
        glossary = build_glossary(node)
        raw = self._call_stt(audio, glossary.hints)
        if not raw.text.strip():
            raise AppError(422, "NO_SPEECH_DETECTED", "Không nhận ra lời nói trong ghi âm")

        if raw.words:
            words = [WordConfidence(word=w["word"], confidence=w["confidence"]) for w in raw.words]
        else:  # adapter chỉ trả độ tin cậy chung ⇒ mọi từ nhận độ tin cậy đó
            words = [WordConfidence(word=w, confidence=raw.confidence) for w in raw.text.split()]
        words = normalize_terms(words, glossary)
        low = [w.word for w in words if w.confidence < self.min_confidence]

        if consent:
            key = f"{AUDIO_PREFIX}{session_id}/{uuid4()}.{fmt.ext}"
            meta = {
                "consent": "true",
                "session-id": str(session_id),
                "retention-days": str(get_settings().audio_retention_days),
            }
            try:
                self.store.put(key, audio, fmt.content_type, meta)
            except Exception as e:  # kho lỗi ⇒ báo rõ, không âm thầm bỏ ghi âm SV đã đồng ý lưu
                log.error("audio.store_failed", extra={"session_id": str(session_id), "error": str(e)})
                raise AppError(503, "AUDIO_STORE_UNAVAILABLE", "Không lưu được ghi âm, thử lại sau") from e
            audio_ref = f"s3://{key}"
        else:
            audio_ref = f"unsaved:{uuid4()}"

        log.info(
            "stt.transcribed",
            extra={
                "session_id": str(session_id),
                "provider": getattr(self.stt, "name", "?"),
                "latency_ms": int((time.perf_counter() - t0) * 1000),
                "bytes": len(audio),
                "confidence": raw.confidence,
                "low_words": len(low),
                "stored": consent,
            },
        )
        return Transcript(
            text=" ".join(w.word for w in words),
            confidence=raw.confidence,
            words=words,
            low_confidence_words=low,
            audio_ref=audio_ref,
            needs_confirmation=raw.confidence < self.min_confidence,
        )


# ------------------------------------------------------------------ TTS đọc câu hỏi (C1-14, FR-TB-10)


class TtsService:
    """Đọc câu hỏi của Tutee thành giọng nói khi SV bật TTS. Tổng hợp theo yêu cầu (lần đầu SV phát) rồi lưu đệm
    vào kho đối tượng `tts/{sessionId}/{turnNo}` để phát lại không tốn thêm lời gọi. Lỗi TTS chỉ làm hỏng việc đọc
    (503 TTS_UNAVAILABLE) – phiên vẫn chạy bằng chữ."""

    def __init__(self, tts: TTSProvider | None = None, storage=None) -> None:
        from app.services.storage import StorageUnavailable, default_storage

        self.tts = tts or get_tts_provider()
        self.storage = storage or default_storage()
        self._unavailable = StorageUnavailable

    def audio_for(self, session_id: UUID, turn_no: int, text: str) -> tuple[bytes, str]:
        content_type = getattr(self.tts, "content_type", "audio/mpeg")
        key = f"tts/{session_id}/{turn_no}"
        url = f"s3://{get_settings().s3_bucket}/{key}"
        try:
            return self.storage.get(url), content_type
        except (KeyError, self._unavailable):
            pass  # chưa có trong đệm (hoặc kho lỗi) ⇒ tổng hợp mới
        name = getattr(self.tts, "name", type(self.tts).__name__)
        try:
            audio = self.tts.synthesize(text)
        except ProviderError as e:
            log.error("tts.error", extra={"provider": name, "error": str(e)})
            raise AppError(503, "TTS_UNAVAILABLE", "Không đọc được câu hỏi lúc này – bạn đọc bằng chữ nhé") from e
        try:
            self.storage.put(key, audio, content_type)
        except self._unavailable:
            log.warning("tts.cache_failed", extra={"session": str(session_id), "turn": turn_no})
        return audio, content_type
