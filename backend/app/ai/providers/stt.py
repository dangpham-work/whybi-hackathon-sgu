"""Adapter STT (mục 6.4.2, NFR-14). Chủ: Đăng (C1-12).

Ba adapter cùng `STTProvider` – nghiệp vụ (`services/speech.py`) không biết đang dùng cái nào:
- `fake`    – LLM_MODE=fake (dev / test / kiểm thử tải): bản chép lời mẫu cố định, không gọi mạng.
- `whisper` – faster-whisper tự host (dịch vụ `stt`, profile `stt` trong Compose) tại STT_WHISPER_URL.
- `cloud`   – dịch vụ đám mây có API tương thích OpenAI (OPENAI_COMPAT_BASE_URL + OPENAI_COMPAT_API_KEY).

Cả `whisper` và `cloud` cùng gọi POST {base}/audio/transcriptions bằng httpx – không thêm SDK, không cài
faster-whisper vào backend. Model Whisper: response_format=verbose_json, timestamp_granularities[]=word.
Model `*-transcribe` (C1-20, mặc định cloud: gpt-4o-mini-transcribe – nhanh hơn, đúng thuật ngữ hơn, rẻ hơn
whisper-1): không hỗ trợ verbose_json ⇒ gửi response_format=json, include[]=logprobs và tính độ tin cậy từ logprobs.
Chọn adapter: STT_PROVIDER hoặc PUT /admin/ai-config (`configure_stt`), không sửa code nghiệp vụ.
"""

import math
import threading
from typing import Any

import httpx

from app.ai.providers.base import (
    PermanentProviderError,
    STTProvider,
    TranscriptResult,
    TransientProviderError,
    classify_http_status,
)
from app.core.config import Settings, get_settings

STT_PROVIDERS = ("fake", "whisper", "cloud")
DEFAULT_MODELS = {"whisper": "Systran/faster-whisper-small", "cloud": "gpt-4o-mini-transcribe", "fake": "fake"}
STT_TIMEOUT_S = 35.0  # ghi âm ≤ 5 phút; quá hạn ⇒ lỗi tạm thời


class FakeSTTProvider:
    """Bản chép lời mẫu cố định (cố ý chứa "con chỏ" và một từ độ tin cậy thấp để thử chuẩn hóa + xác nhận)."""

    name = "fake"
    model = "fake"
    SAMPLE: tuple[tuple[str, float], ...] = (
        ("Con", 0.97),
        ("chỏ", 0.62),
        ("là", 0.98),
        ("biến", 0.95),
        ("lưu", 0.93),
        ("địa", 0.96),
        ("chỉ", 0.96),
        ("của", 0.97),
        ("một", 0.98),
        ("biến", 0.95),
        ("khác.", 0.94),
    )

    def transcribe(self, audio: bytes, lang: str = "vi", hints: list[str] | None = None) -> TranscriptResult:
        words = [{"word": w, "confidence": c} for w, c in self.SAMPLE]
        conf = sum(c for _, c in self.SAMPLE) / len(self.SAMPLE)
        return TranscriptResult(text=" ".join(w for w, _ in self.SAMPLE), confidence=round(conf, 4), words=words)


class WhisperHTTPProvider:
    """API phiên âm tương thích OpenAI – dùng cho faster-whisper-server tự host và dịch vụ đám mây."""

    def __init__(
        self,
        name: str,
        base_url: str,
        model: str,
        api_key: str = "",
        *,
        timeout_s: float = STT_TIMEOUT_S,
        http_client: httpx.Client | None = None,
    ):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.http = http_client or httpx.Client(timeout=timeout_s)

    def transcribe(self, audio: bytes, lang: str = "vi", hints: list[str] | None = None) -> TranscriptResult:
        logprobs = uses_logprobs(self.model)
        data: dict[str, Any] = {"model": self.model, "language": lang}
        if logprobs:
            data |= {"response_format": "json", "include[]": "logprobs"}
        else:
            data |= {"response_format": "verbose_json", "timestamp_granularities[]": "word"}
        if hints:
            # Whisper dùng `prompt` làm ngữ cảnh: liệt kê thuật ngữ của nút để nhận đúng chính tả.
            data["prompt"] = ", ".join(hints)[:800]
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            r = self.http.post(
                f"{self.base_url}/audio/transcriptions",
                data=data,
                files={"file": (f"audio.{audio_extension(audio)}", audio, "application/octet-stream")},
                headers=headers,
            )
        except httpx.TimeoutException as e:
            raise TransientProviderError(f"stt {self.name} timeout: {e}") from e
        except httpx.TransportError as e:
            raise TransientProviderError(f"stt {self.name} mạng lỗi: {e}") from e
        if r.status_code >= 400:
            raise classify_http_status(r.status_code)(f"stt {self.name} {r.status_code}: {r.text[:300]}")
        try:
            body = r.json()
        except ValueError as e:
            raise TransientProviderError(f"stt {self.name}: phản hồi không phải JSON") from e
        return parse_logprobs_json(body) if logprobs else parse_verbose_json(body)


def audio_extension(audio: bytes) -> str:
    """Đuôi tệp theo chữ ký byte (cùng bảng với services/speech.sniff_audio). API OpenAI đoán định dạng theo tên
    tệp: gửi "audio" không đuôi ⇒ 400 Unsupported file format. Không nhận ra ⇒ "webm" (MediaRecorder mặc định)."""
    if audio.startswith(b"OggS"):
        return "ogg"
    if audio[:4] == b"RIFF" and audio[8:12] == b"WAVE":
        return "wav"
    if audio.startswith(b"ID3") or (len(audio) > 1 and audio[0] == 0xFF and audio[1] & 0xE0 == 0xE0):
        return "mp3"
    if audio[4:8] == b"ftyp":
        return "m4a"
    return "webm"


def uses_logprobs(model: str) -> bool:
    """gpt-4o-transcribe / gpt-4o-mini-transcribe… chỉ trả json (+ logprobs), không có verbose_json."""
    return "transcribe" in model.lower()


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def parse_verbose_json(body: dict[str, Any]) -> TranscriptResult:
    """verbose_json → TranscriptResult. Độ tin cậy từng từ: `probability` (faster-whisper); thiếu thì lấy
    exp(avg_logprob) của đoạn chứa từ. Không có số đo nhận dạng nào ⇒ 0.0 (bảo thủ, buộc SV xác nhận):
    `no_speech_prob` chỉ cho biết có tiếng nói, không cho biết chép đúng. Sai kiểu ⇒ PermanentProviderError."""
    if not isinstance(body, dict) or not isinstance(body.get("text"), str):
        raise PermanentProviderError("stt: phản hồi thiếu trường text")
    try:
        return _parse_verbose_json(body)
    except (TypeError, ValueError, OverflowError) as e:
        raise PermanentProviderError(f"stt: độ tin cậy sai kiểu: {e}") from e


def _parse_verbose_json(body: dict[str, Any]) -> TranscriptResult:
    segments = [s for s in body.get("segments") or [] if isinstance(s, dict)]

    def seg_conf(t: float | None) -> float | None:
        for s in segments:
            start, end = s.get("start"), s.get("end")
            if t is None or (start is not None and end is not None and start <= t <= end):
                if s.get("avg_logprob") is not None:
                    return _clamp(math.exp(float(s["avg_logprob"])))
        return None

    raw_words = body.get("words") or [w for s in segments for w in (s.get("words") or [])]
    words: list[dict[str, Any]] = []
    for w in raw_words:
        if not isinstance(w, dict) or not str(w.get("word", "")).strip():
            continue
        if w.get("probability") is not None:
            c = _clamp(w["probability"])
        else:
            c = seg_conf(w.get("start"))
            if c is None:
                c = seg_conf(None)
        words.append({"word": str(w["word"]).strip(), "confidence": 0.0 if c is None else c})

    if words:
        conf = sum(w["confidence"] for w in words) / len(words)
    else:
        seg_values = [c for c in (seg_conf(s.get("start")) for s in segments) if c is not None]
        conf = sum(seg_values) / len(seg_values) if seg_values else 0.0
    return TranscriptResult(text=body["text"].strip(), confidence=round(_clamp(conf), 4), words=words)


def parse_logprobs_json(body: dict[str, Any]) -> TranscriptResult:
    """json + logprobs → TranscriptResult. Gom token thành từ (token mở đầu bằng khoảng trắng là từ mới); độ tin
    cậy của từ = xác suất token yếu nhất trong từ. Không có logprobs ⇒ 0.0 (bảo thủ, buộc SV xác nhận ở SV-05)."""
    if not isinstance(body, dict) or not isinstance(body.get("text"), str):
        raise PermanentProviderError("stt: phản hồi thiếu trường text")
    try:
        groups: list[list[Any]] = []  # [chữ, xác suất nhỏ nhất]
        for t in body.get("logprobs") or []:
            if not isinstance(t, dict):
                continue
            token, prob = str(t.get("token", "")), _clamp(math.exp(float(t["logprob"])))
            if not groups or token[:1].isspace():
                groups.append([token, prob])
            else:
                groups[-1][0] += token
                groups[-1][1] = min(groups[-1][1], prob)
    except (KeyError, TypeError, ValueError, OverflowError) as e:
        raise PermanentProviderError(f"stt: logprobs sai kiểu: {e}") from e
    words = [{"word": w.strip(), "confidence": round(c, 4)} for w, c in groups if w.strip()]
    conf = sum(w["confidence"] for w in words) / len(words) if words else 0.0
    return TranscriptResult(text=body["text"].strip(), confidence=round(_clamp(conf), 4), words=words)


# ------------------------------------------------------------------ chọn adapter theo cấu hình

_override: dict[str, str | None] = {}  # PUT /admin/ai-config ghi đè khi chạy (C2-06 sẽ lưu CSDL)
_lock = threading.Lock()
_current: STTProvider | None = None


def build_stt_provider(settings: Settings, override: dict[str, str | None] | None = None) -> STTProvider:
    """LLM_MODE=fake luôn dùng fake (test / dev không gọi mạng)."""
    o = override or {}
    if settings.llm_mode == "fake":
        return FakeSTTProvider()
    name = o.get("provider") or settings.stt_provider
    model = o.get("model") or DEFAULT_MODELS.get(name, "")
    if name == "fake":
        return FakeSTTProvider()
    if name == "whisper":
        return WhisperHTTPProvider("whisper", f"{settings.stt_whisper_url.rstrip('/')}/v1", model)
    if name == "cloud":
        if not settings.openai_compat_base_url:
            raise PermanentProviderError("STT cloud cần OPENAI_COMPAT_BASE_URL")
        return WhisperHTTPProvider("cloud", settings.openai_compat_base_url, model, settings.openai_compat_api_key)
    raise PermanentProviderError(f"STT_PROVIDER không hỗ trợ: {name!r} (chọn {', '.join(STT_PROVIDERS)})")


def get_stt_provider() -> STTProvider:
    global _current
    with _lock:
        if _current is None:
            _current = build_stt_provider(get_settings(), _override)
        return _current


def configure_stt(provider: str, model: str | None = None) -> None:
    """PUT /admin/ai-config: đổi adapter STT lúc chạy. `model` rỗng / "default" ⇒ model mặc định của adapter."""
    global _current
    if provider not in STT_PROVIDERS:
        raise ValueError(f"STT provider không hỗ trợ: {provider!r}")
    with _lock:
        _override.clear()
        _override.update({"provider": provider, "model": None if model in (None, "", "default") else model})
        _current = None


def reset_stt() -> None:
    global _current
    with _lock:
        _override.clear()
        _current = None
