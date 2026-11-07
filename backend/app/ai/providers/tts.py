"""Adapter TTS (mục 6.4.4, NFR-14). Chủ: Đăng (C1-14).

Hai adapter cùng `TTSProvider` – nghiệp vụ (`services/speech.py`) không biết đang dùng cái nào:
- `fake`  – LLM_MODE=fake (dev / test): một đoạn WAV im lặng ngắn, không gọi mạng.
- `cloud` – dịch vụ đám mây có API tương thích OpenAI (OPENAI_COMPAT_BASE_URL + OPENAI_COMPAT_API_KEY):
  POST {base}/audio/speech {model, input, voice, response_format: "mp3"} → mp3.
Chọn adapter: TTS_PROVIDER hoặc PUT /admin/ai-config (`configure_tts`).
"""

import io
import threading
import wave

import httpx

from app.ai.providers.base import (
    PermanentProviderError,
    TransientProviderError,
    TTSProvider,
    classify_http_status,
)
from app.core.config import Settings, get_settings

TTS_PROVIDERS = ("fake", "cloud")
DEFAULT_MODELS = {"cloud": "tts-1", "fake": "fake"}
DEFAULT_VOICE = "alloy"  # giọng đa ngữ của API tương thích OpenAI; đọc được tiếng Việt
TTS_TIMEOUT_S = 15.0
MAX_TEXT_CHARS = 1000  # độ dài tối đa của Question.text


def _silence_wav() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 800)  # 0,1 giây
    return buf.getvalue()


class FakeTTSProvider:
    name = "fake"
    model = "fake"
    content_type = "audio/wav"

    def synthesize(self, text: str, voice: str = "vi-VN") -> bytes:
        return _silence_wav()


class CloudTTSProvider:
    """API đọc văn bản tương thích OpenAI."""

    content_type = "audio/mpeg"

    def __init__(self, base_url: str, model: str, api_key: str = "", client: httpx.Client | None = None) -> None:
        self.name = "cloud"
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client = client or httpx.Client(timeout=TTS_TIMEOUT_S)

    def synthesize(self, text: str, voice: str = "vi-VN") -> bytes:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        body = {"model": self.model, "input": text[:MAX_TEXT_CHARS], "voice": DEFAULT_VOICE, "response_format": "mp3"}
        try:
            r = self._client.post(f"{self.base_url}/audio/speech", json=body, headers=headers)
        except httpx.TimeoutException as e:
            raise TransientProviderError(f"tts timeout: {e}") from e
        except httpx.TransportError as e:
            raise TransientProviderError(f"tts mạng lỗi: {e}") from e
        if r.status_code >= 400:
            raise classify_http_status(r.status_code)(f"tts {r.status_code}: {r.text[:300]}")
        if not r.content:
            raise PermanentProviderError("tts: phản hồi rỗng")
        return r.content


# ------------------------------------------------------------------ chọn adapter theo cấu hình

_override: dict[str, str | None] = {}  # PUT /admin/ai-config ghi đè khi chạy
_lock = threading.Lock()
_current: TTSProvider | None = None


def build_tts_provider(settings: Settings, override: dict[str, str | None] | None = None) -> TTSProvider:
    """LLM_MODE=fake luôn dùng fake (test / dev không gọi mạng)."""
    o = override or {}
    name = o.get("provider") or settings.tts_provider
    if settings.llm_mode == "fake" or name == "fake":
        return FakeTTSProvider()
    if name == "cloud":
        if not settings.openai_compat_base_url:
            raise PermanentProviderError("TTS cloud cần OPENAI_COMPAT_BASE_URL")
        model = o.get("model") or DEFAULT_MODELS["cloud"]
        return CloudTTSProvider(settings.openai_compat_base_url, model, settings.openai_compat_api_key)
    raise PermanentProviderError(f"TTS_PROVIDER không hỗ trợ: {name!r} (chọn {', '.join(TTS_PROVIDERS)})")


def get_tts_provider() -> TTSProvider:
    global _current
    with _lock:
        if _current is None:
            _current = build_tts_provider(get_settings(), _override)
        return _current


def configure_tts(provider: str, model: str | None = None) -> None:
    """PUT /admin/ai-config: đổi adapter TTS lúc chạy. `model` rỗng / "default" ⇒ model mặc định của adapter."""
    global _current
    if provider not in TTS_PROVIDERS:
        raise ValueError(f"TTS provider không hỗ trợ: {provider!r}")
    with _lock:
        _override.clear()
        _override.update({"provider": provider, "model": None if model in (None, "", "default") else model})
        _current = None


def reset_tts() -> None:
    global _current
    with _lock:
        _override.clear()
        _current = None
