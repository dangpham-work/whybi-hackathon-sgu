"""C1-12 – adapter STT: chọn theo cấu hình, parse verbose_json, lỗi nhà cung cấp."""

import httpx
import pytest

from app.ai.providers import stt as stt_mod
from app.ai.providers.base import PermanentProviderError, TransientProviderError
from app.ai.providers.stt import (
    FakeSTTProvider,
    WhisperHTTPProvider,
    build_stt_provider,
    configure_stt,
    parse_verbose_json,
    reset_stt,
)
from app.core.config import Settings


@pytest.fixture(autouse=True)
def _reset():
    yield
    reset_stt()


def _settings(**kw) -> Settings:
    return Settings(_env_file=None, **kw)


def test_fake_mode_always_uses_fake_provider():
    p = build_stt_provider(_settings(llm_mode="fake", stt_provider="cloud"), {"provider": "whisper"})
    assert isinstance(p, FakeSTTProvider)


def test_real_mode_selects_adapter_by_config_without_code_change():
    w = build_stt_provider(_settings(llm_mode="real", stt_provider="whisper", stt_whisper_url="http://stt:8000/"))
    assert isinstance(w, WhisperHTTPProvider) and w.name == "whisper"
    assert w.base_url == "http://stt:8000/v1"
    assert w.model == stt_mod.DEFAULT_MODELS["whisper"]

    c = build_stt_provider(
        _settings(llm_mode="real", stt_provider="cloud", openai_compat_base_url="https://api.x/v1"),
        {"provider": None, "model": "whisper-large-v3"},
    )
    assert isinstance(c, WhisperHTTPProvider) and c.name == "cloud"
    assert c.base_url == "https://api.x/v1" and c.model == "whisper-large-v3"


def test_override_from_admin_wins_over_env():
    p = build_stt_provider(_settings(llm_mode="real", stt_provider="cloud"), {"provider": "fake"})
    assert isinstance(p, FakeSTTProvider)


def test_cloud_without_base_url_and_unknown_provider_fail_loudly():
    with pytest.raises(PermanentProviderError):
        build_stt_provider(_settings(llm_mode="real", stt_provider="cloud", openai_compat_base_url=""))
    with pytest.raises(PermanentProviderError):
        build_stt_provider(_settings(llm_mode="real", stt_provider="google"))


def test_configure_stt_validates_provider():
    with pytest.raises(ValueError):
        configure_stt("google")
    configure_stt("whisper", "default")
    assert stt_mod._override == {"provider": "whisper", "model": None}


def test_parse_word_probability():
    r = parse_verbose_json(
        {
            "text": " con trỏ ",
            "words": [{"word": " con", "probability": 0.9}, {"word": " trỏ", "probability": 0.4}],
        }
    )
    assert r.text == "con trỏ"
    assert r.words == [{"word": "con", "confidence": 0.9}, {"word": "trỏ", "confidence": 0.4}]
    assert r.confidence == pytest.approx(0.65)


def test_parse_falls_back_to_segment_logprob():
    r = parse_verbose_json(
        {
            "text": "a b",
            "segments": [{"start": 0, "end": 2, "avg_logprob": -0.5, "words": [{"word": "a", "start": 0.1}]}],
            "words": [{"word": "a", "start": 0.1}, {"word": "b", "start": 5}],
        }
    )
    assert r.words[0]["confidence"] == pytest.approx(0.6065, abs=1e-3)
    assert r.words[1]["confidence"] == pytest.approx(0.6065, abs=1e-3)  # ngoài đoạn ⇒ lấy đoạn đầu


def test_parse_rejects_body_without_text():
    with pytest.raises(PermanentProviderError):
        parse_verbose_json({"segments": []})


def _provider(handler) -> WhisperHTTPProvider:
    return WhisperHTTPProvider(
        "whisper", "http://stt:8000/v1", "m", http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )


def test_whisper_posts_multipart_with_hints():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        seen["body"] = req.content
        return httpx.Response(200, json={"text": "con trỏ", "words": [{"word": "con", "probability": 0.9}]})

    r = _provider(handler).transcribe(b"RIFFxxxxWAVE", "vi", ["con trỏ", "free()"])
    assert seen["url"] == "http://stt:8000/v1/audio/transcriptions"
    assert b'name="language"' in seen["body"] and b"vi" in seen["body"]
    assert "con trỏ, free()".encode() in seen["body"]
    assert b"verbose_json" in seen["body"]
    assert r.text == "con trỏ"


@pytest.mark.parametrize(
    "body",
    [
        {"text": "xin chào"},
        {"text": "xin chào", "words": [{"word": "xin"}, {"word": "chào"}]},
        {"text": "xin chào", "segments": [{"start": 0, "end": 1, "no_speech_prob": 0}]},
        {
            "text": "xin chào",
            "words": [{"word": "xin", "start": 0}, {"word": "chào", "start": 0.5}],
            "segments": [{"start": 0, "end": 1, "no_speech_prob": 0}],
        },
    ],
)
def test_missing_recognition_confidence_is_conservative(body):
    result = _provider(lambda req: httpx.Response(200, json=body)).transcribe(b"x")
    assert result.confidence == 0.0
    assert all(w["confidence"] == 0.0 for w in result.words)


@pytest.mark.parametrize(
    "body",
    [
        {"text": "xin chào", "words": [{"word": "xin", "probability": "unknown"}]},
        {"text": "xin chào", "segments": [{"start": 0, "end": 1, "avg_logprob": [1]}]},
    ],
)
def test_malformed_confidence_raises_provider_error(body):
    # Dịch vụ trả sai kiểu ⇒ ProviderError (SpeechService đổi thành AppError), không để ValueError thành 500.
    with pytest.raises(PermanentProviderError):
        _provider(lambda req: httpx.Response(200, json=body)).transcribe(b"x")


@pytest.mark.parametrize(("status", "exc"), [(503, TransientProviderError), (401, PermanentProviderError)])
def test_whisper_http_errors_are_classified(status, exc):
    with pytest.raises(exc):
        _provider(lambda req: httpx.Response(status, text="lỗi")).transcribe(b"x")


def test_whisper_timeout_is_transient():
    def handler(req):
        raise httpx.ReadTimeout("chậm", request=req)

    with pytest.raises(TransientProviderError):
        _provider(handler).transcribe(b"x")
