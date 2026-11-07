"""C1-14 – adapter TTS: fake (WAV hợp lệ), cloud (API tương thích OpenAI), phân loại lỗi, chọn adapter."""

import io
import json
import wave

import httpx
import pytest

from app.ai.providers.base import PermanentProviderError, TransientProviderError
from app.ai.providers.tts import (
    CloudTTSProvider,
    FakeTTSProvider,
    build_tts_provider,
    configure_tts,
    get_tts_provider,
    reset_tts,
)
from app.core.config import Settings


@pytest.fixture(autouse=True)
def _reset():
    reset_tts()
    yield
    reset_tts()


def cloud(handler) -> CloudTTSProvider:
    return CloudTTSProvider(
        "https://tts.example/v1/", "tts-1", "k", httpx.Client(transport=httpx.MockTransport(handler))
    )


def test_fake_tra_wav_hop_le():
    audio = FakeTTSProvider().synthesize("Con trỏ là gì?")
    with wave.open(io.BytesIO(audio)) as w:
        assert w.getnframes() > 0


def test_cloud_goi_dung_endpoint_va_tra_mp3():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"], seen["auth"], seen["body"] = str(req.url), req.headers["authorization"], req.read()
        return httpx.Response(200, content=b"ID3mp3")

    assert cloud(handler).synthesize("Xin chào") == b"ID3mp3"
    assert seen["url"] == "https://tts.example/v1/audio/speech" and seen["auth"] == "Bearer k"
    sent = json.loads(seen["body"])
    assert sent["model"] == "tts-1" and sent["input"] == "Xin chào" and sent["response_format"] == "mp3"


@pytest.mark.parametrize(
    ("status", "exc"),
    [
        (429, TransientProviderError),
        (503, TransientProviderError),
        (401, PermanentProviderError),
        (400, PermanentProviderError),
    ],
)
def test_cloud_phan_loai_loi_http(status, exc):
    with pytest.raises(exc):
        cloud(lambda r: httpx.Response(status, text="x")).synthesize("a")


def test_cloud_timeout_la_loi_tam_thoi_va_rong_la_vinh_vien():
    def boom(req):
        raise httpx.ReadTimeout("chậm")

    with pytest.raises(TransientProviderError):
        cloud(boom).synthesize("a")
    with pytest.raises(PermanentProviderError):
        cloud(lambda r: httpx.Response(200, content=b"")).synthesize("a")


def test_build_theo_cau_hinh():
    assert isinstance(build_tts_provider(Settings(llm_mode="fake")), FakeTTSProvider)
    real = Settings(llm_mode="real", tts_provider="cloud", openai_compat_base_url="https://x/v1")
    assert isinstance(build_tts_provider(real), CloudTTSProvider)
    with pytest.raises(PermanentProviderError):
        build_tts_provider(Settings(llm_mode="real", tts_provider="cloud", openai_compat_base_url=""))
    with pytest.raises(PermanentProviderError):
        build_tts_provider(Settings(llm_mode="real", tts_provider="google"))


def test_configure_doi_adapter_luc_chay():
    configure_tts("fake", "default")
    assert isinstance(get_tts_provider(), FakeTTSProvider)
    with pytest.raises(ValueError):
        configure_tts("google")
