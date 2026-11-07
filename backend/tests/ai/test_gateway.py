"""C1-02 – LLM Adapter (gateway + providers). Không gọi mạng: provider giả theo kịch bản.

Xong khi: đổi nhà cung cấp trong cấu hình mà không sửa code nghiệp vụ; model chính lỗi thì tự chuyển
sang model dự phòng.
"""

import json
import logging
from typing import Any

import httpx
import pytest

from app.ai.gateway import InMemoryTokenStore, LLMGateway, RedisTokenStore, build_gateway
from app.ai.providers import FakeProvider, GeminiProvider, OpenAICompatProvider
from app.ai.providers.base import LLMResult, PermanentProviderError, TransientProviderError, provider_json_schema
from app.core.config import Settings
from app.core.errors import AppError
from app.models.enums import QuestionStrategy
from app.models.schemas.session import JudgeResult, Question

MSG = [
    {"role": "system", "content": "Bạn là Tutee"},
    {"role": "user", "content": "<student_transcript>x</student_transcript>"},
]
GOOD = {"text": "Nếu hai con trỏ cùng trỏ một ô thì sao?", "strategy": "EDGE_CASE", "targetPointId": "SC1"}


class ScriptedProvider:
    """Trả lần lượt theo kịch bản: dict → JSON đúng, str → văn bản thô, Exception → ném lỗi."""

    def __init__(self, name: str, script: list[Any], model: str = "m"):
        self.name = name
        self.model = model
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []

    def complete(self, messages, schema, *, model, temperature=0):
        self.calls.append({"messages": messages, "schema": schema, "model": model, "temperature": temperature})
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, dict):
            return LLMResult(data=item, model=model, input_tokens=100, output_tokens=20, latency_ms=5)
        return LLMResult(data=None, raw_text=item, model=model, input_tokens=100, output_tokens=20, latency_ms=5)

    def embed(self, texts):
        return [[0.0] for _ in texts]


def _gw(primary, fallback=None, **kw) -> LLMGateway:
    kw.setdefault("sleep", lambda s: None)
    return LLMGateway(primary, fallback, **kw)


# --- ép schema, thử lại khi JSON hỏng ---------------------------------------------------------


def test_returns_validated_instance():
    p = ScriptedProvider("a", [GOOD])
    q = _gw(p).call_json(Question, MSG)
    assert isinstance(q, Question) and q.strategy == QuestionStrategy.EDGE_CASE
    assert p.calls[0]["temperature"] == 0


def test_schema_is_sent_to_provider():
    p = ScriptedProvider("a", [GOOD])
    _gw(p).call_json(Question, MSG)
    sent = p.calls[0]["schema"]
    assert "text" in sent["properties"] and sent.get("type") == "object"


def test_retry_when_json_broken_then_ok():
    p = ScriptedProvider("a", ['{"text": "thiếu ngoặc', GOOD])
    q = _gw(p).call_json(Question, MSG)
    assert q.text == GOOD["text"] and len(p.calls) == 2
    # lần 2 có kèm thông báo lỗi để model tự sửa (UC06 luồng 4a), không mất prompt gốc
    retry_msgs = p.calls[1]["messages"]
    assert retry_msgs[: len(MSG)] == MSG
    assert "JSON" in retry_msgs[-1]["content"]


def test_retry_when_schema_validation_fails():
    p = ScriptedProvider("a", [{"text": ""}, GOOD])  # text rỗng vi phạm min_length
    assert _gw(p).call_json(Question, MSG).text == GOOD["text"]
    assert len(p.calls) == 2
    assert "text" in p.calls[1]["messages"][-1]["content"]


def test_accepts_json_inside_markdown_fence():
    p = ScriptedProvider("a", ["```json\n" + json.dumps(GOOD) + "\n```"])
    assert _gw(p).call_json(Question, MSG).target_point_id == "SC1"


# --- model dự phòng ---------------------------------------------------------------------------


def test_fallback_after_parse_retries_exhausted():
    p = ScriptedProvider("a", ["hỏng", "hỏng", "hỏng"])
    f = ScriptedProvider("b", [GOOD], model="dự-phòng")
    q = _gw(p, f, max_retries=2).call_json(Question, MSG)
    assert q.text == GOOD["text"]
    assert len(p.calls) == 3 and f.calls[0]["model"] == "dự-phòng"


def test_transient_error_retried_on_same_provider():
    p = ScriptedProvider("a", [TransientProviderError("503"), GOOD])
    f = ScriptedProvider("b", [])
    _gw(p, f, transient_retries=1).call_json(Question, MSG)
    assert len(p.calls) == 2 and f.calls == []


def test_primary_down_switches_to_fallback():
    p = ScriptedProvider("a", [TransientProviderError("timeout"), TransientProviderError("timeout")])
    f = ScriptedProvider("b", [GOOD])
    q = _gw(p, f, transient_retries=1).call_json(Question, MSG)
    assert q.text == GOOD["text"] and len(f.calls) == 1


def test_permanent_error_goes_straight_to_fallback():
    p = ScriptedProvider("a", [PermanentProviderError("401 sai khóa")])
    f = ScriptedProvider("b", [GOOD])
    _gw(p, f, transient_retries=3).call_json(Question, MSG)
    assert len(p.calls) == 1 and len(f.calls) == 1


def test_model_override_only_applies_to_primary():
    p = ScriptedProvider("a", [PermanentProviderError("x")], model="flash")
    f = ScriptedProvider("b", [GOOD], model="fb")
    _gw(p, f).call_json(Question, MSG, model="flash-lite")
    assert p.calls[0]["model"] == "flash-lite" and f.calls[0]["model"] == "fb"


def test_all_providers_fail_raises_503():
    p = ScriptedProvider("a", [PermanentProviderError("x")])
    f = ScriptedProvider("b", [PermanentProviderError("y")])
    with pytest.raises(AppError) as e:
        _gw(p, f).call_json(Question, MSG)
    assert e.value.status == 503 and e.value.code == "LLM_UNAVAILABLE"


def test_503_details_do_not_leak_provider_error_body():
    p = ScriptedProvider("a", [PermanentProviderError("401: org-bi-mat project=noi-bo")])
    with pytest.raises(AppError) as e:
        _gw(p).call_json(Question, MSG)
    assert e.value.details == {"attempts": [{"provider": "a", "model": "m", "error": "PermanentProviderError"}]}
    assert "bi-mat" not in json.dumps(e.value.details)


def test_configure_closes_old_gateway(monkeypatch):
    from app.ai import gateway as gw_mod

    closed = []
    old = gw_mod.get_gateway()
    monkeypatch.setattr(old, "close", lambda: closed.append(True))
    gw_mod.configure_llm("fake", "fake")
    assert closed == [True] and gw_mod.get_gateway() is not old
    gw_mod.reset_gateway()


# --- cache, ngân sách token, log --------------------------------------------------------------


def test_cache_hits_for_identical_call():
    p = ScriptedProvider("a", [GOOD, GOOD])
    gw = _gw(p)
    a = gw.call_json(Question, MSG)
    b = gw.call_json(Question, MSG)
    assert a == b and len(p.calls) == 1
    gw.call_json(Question, MSG + [{"role": "user", "content": "khác"}])
    assert len(p.calls) == 2


def test_cache_can_be_bypassed():
    p = ScriptedProvider("a", [GOOD, GOOD])
    gw = _gw(p)
    gw.call_json(Question, MSG)
    gw.call_json(Question, MSG, use_cache=False)
    assert len(p.calls) == 2


def test_session_token_budget_enforced():
    p = ScriptedProvider("a", [GOOD, GOOD, GOOD])  # mỗi lượt 120 token
    gw = _gw(p, token_budget=200)
    gw.call_json(Question, MSG, session_id="s1", use_cache=False)
    gw.call_json(Question, MSG, session_id="s1", use_cache=False)  # đã dùng 240 ≥ 200
    with pytest.raises(AppError) as e:
        gw.call_json(Question, MSG, session_id="s1", use_cache=False)
    assert e.value.status == 429 and e.value.code == "TOKEN_BUDGET_EXCEEDED"
    assert gw.tokens_used("s1") == 240
    gw.call_json(Question, MSG, session_id="s2", use_cache=False)  # phiên khác không ảnh hưởng


class FakeTokenRedis:
    """Các client độc lập dùng chung dữ liệu, không cần Redis thật hay thư viện mới."""

    def __init__(self, data):
        self.data = data
        self.expirations = {}
        self.failure = None
        self.closed = False
        self.attempts = []

    def _check(self, operation):
        from redis.exceptions import ConnectionError

        self.attempts.append(operation)
        if self.failure == operation:
            raise ConnectionError("redis://secret@example.invalid/0")

    def get(self, key):
        self._check("get")
        return self.data.get(key)

    def eval(self, script, numkeys, key, cursor_key, delta, target, ttl_s):
        assert numkeys == 2
        self._check("execute")
        previous = self.data.get(cursor_key)
        self.data[key] = self.data.get(key, 0) + (delta if previous is None else target - previous)
        self.data[cursor_key] = target
        self.expirations[key] = self.expirations[cursor_key] = ttl_s
        self._check("execute_after")
        return self.data[key]

    def close(self):
        self.closed = True


@pytest.fixture
def redis_budget(monkeypatch):
    import redis

    from app.ai import gateway as gw_mod

    data = {}
    clients = []

    def new_client(*a, **kw):
        client = FakeTokenRedis(data)
        clients.append(client)
        return client

    monkeypatch.setattr(redis.Redis, "from_url", new_client)
    monkeypatch.setattr(gw_mod, "build_provider", lambda *a: ScriptedProvider("a", [GOOD, GOOD]))
    settings = Settings(
        _env_file=None,
        app_env="prod",
        llm_mode="real",
        llm_fallback_provider="",
        llm_session_token_budget=200,
        redis_url="redis://test/0",
    )
    return settings, data, clients


def test_session_budget_shared_across_gateway_instances(redis_budget):
    settings, _, _ = redis_budget
    first, second = build_gateway(settings), build_gateway(settings)
    first.call_json(Question, MSG, session_id="shared", use_cache=False)
    second.call_json(Question, MSG, session_id="shared", use_cache=False)
    with pytest.raises(AppError) as error:
        first.call_json(Question, MSG, session_id="shared", use_cache=False)
    assert error.value.code == "TOKEN_BUDGET_EXCEEDED" and error.value.status == 429
    assert error.value.details == {"sessionId": "shared", "used": 240, "budget": 200}
    assert first.tokens_used("shared") == second.tokens_used("shared") == 240
    assert build_gateway(settings).tokens_used("shared") == 240  # dựng lại không mất số đếm
    assert len(first.primary.calls) == len(second.primary.calls) == 1


def test_redis_budget_sets_ttl_and_keeps_sessions_separate(redis_budget):
    settings, data, clients = redis_budget
    gw = build_gateway(settings)
    gw.call_json(Question, MSG, session_id="one", use_cache=False)
    gw.call_json(Question, MSG, session_id="two", use_cache=False)
    assert {key: value for key, value in data.items() if key.startswith("llm:tokens:")} == {
        "llm:tokens:one": 120,
        "llm:tokens:two": 120,
    }
    assert clients[0].expirations["llm:tokens:one"] == clients[0].expirations["llm:tokens:two"] == 604800
    assert set(clients[0].expirations.values()) == {604800}
    gw.close()
    assert clients[0].closed


@pytest.mark.parametrize("operation", ["get", "execute"])
def test_redis_recovers_after_cooldown_and_reconciles_offline_tokens(operation):
    now = 100.0
    data = {}
    client = FakeTokenRedis(data)
    store = RedisTokenStore(client, ttl_s=600, clock=lambda: now)
    other = RedisTokenStore(FakeTokenRedis(data), ttl_s=600)
    assert store.increment("one", 100) == 100
    assert store.increment("two", 20) == 20

    client.failure = operation
    if operation == "get":
        assert store.get("one") == 100
    assert store.increment("one", 30) == 130
    assert store.increment("two", 15) == 35
    attempts = list(client.attempts)
    client.failure = None
    now = 129.0
    assert store.get("one") == 130
    assert store.increment("one", 10) == 140
    assert client.attempts == attempts

    assert other.increment("one", 7) == 107
    now = 130.0
    assert store.increment("one", 50) == 197
    assert other.get("one") == 197
    assert other.get("two") == 35
    assert store.get("one") == 197
    assert store.get("one") == 197
    assert client.expirations["llm:tokens:one"] == client.expirations["llm:tokens:two"] == 600


def test_redis_lost_write_reply_does_not_duplicate_tokens_on_retry():
    now = 100.0
    data = {}
    client = FakeTokenRedis(data)
    store = RedisTokenStore(client, ttl_s=600, clock=lambda: now)
    assert store.increment("one", 100) == 100
    client.failure = "execute_after"
    assert store.increment("one", 30) == 130
    assert store.increment("one", 10) == 140
    assert data["llm:tokens:one"] == 130

    client.failure = None
    now = 130.0
    assert store.get("one") == 140
    assert RedisTokenStore(FakeTokenRedis(data), ttl_s=600).get("one") == 140
    assert store.increment("one", 5) == 145
    assert store.get("one") == 145


@pytest.mark.parametrize("operation", ["get", "execute"])
def test_redis_failure_keeps_known_usage_and_warns(redis_budget, caplog, operation):
    settings, _, clients = redis_budget
    gw = build_gateway(settings)
    gw.call_json(Question, MSG, session_id="outage", use_cache=False)
    clients[0].failure = operation
    with caplog.at_level(logging.WARNING, logger="app.ai.gateway"):
        gw.call_json(Question, MSG, session_id="outage", use_cache=False)
    assert gw.tokens_used("outage") == 240
    clients[0].failure = None  # vẫn dùng RAM khi chưa hết khoảng nghỉ
    with pytest.raises(AppError) as error:
        gw.call_json(Question, MSG, session_id="outage", use_cache=False)
    assert error.value.code == "TOKEN_BUDGET_EXCEEDED"
    warnings = [r for r in caplog.records if getattr(r, "event", "") == "llm.token_store_fallback"]
    assert len(warnings) == 1 and warnings[0].levelno == logging.WARNING
    assert "secret" not in caplog.text
    assert len(gw.primary.calls) == 2


@pytest.mark.parametrize(
    "mode,env,url", [("fake", "prod", "redis://test/0"), ("real", "test", "redis://test/0"), ("real", "prod", "")]
)
def test_memory_budget_default_in_fake_test_or_without_redis(redis_budget, mode, env, url):
    settings, _, clients = redis_budget
    settings.llm_mode, settings.app_env, settings.redis_url = mode, env, url
    gw = build_gateway(settings)
    assert isinstance(gw._token_store, InMemoryTokenStore)
    assert clients == []


def test_memory_token_store_can_be_shared_explicitly():
    store = InMemoryTokenStore()
    first = _gw(ScriptedProvider("a", [GOOD]), token_budget=120, token_store=store)
    second = _gw(ScriptedProvider("b", []), token_budget=120, token_store=store)
    first.call_json(Question, MSG, session_id="same")
    with pytest.raises(AppError) as error:
        second.call_json(Question, MSG, session_id="same")
    assert error.value.code == "TOKEN_BUDGET_EXCEEDED"
    assert second.primary.calls == []


@pytest.mark.parametrize("max_retries", [0, 2])
def test_budget_stops_json_retry_and_fallback(max_retries):
    primary = ScriptedProvider("a", ["hỏng"] * 3)
    fallback = ScriptedProvider("b", [GOOD])
    gw = _gw(primary, fallback, max_retries=max_retries, token_budget=120)
    with pytest.raises(AppError) as error:
        gw.call_json(Question, MSG, session_id="limited")
    assert error.value.code == "TOKEN_BUDGET_EXCEEDED"
    assert len(primary.calls) == 1
    assert fallback.calls == []
    assert gw.tokens_used("limited") == 120


def test_cache_eviction_before_reader_acquires_lock_is_a_miss():
    provider = ScriptedProvider("a", [GOOD, GOOD])
    gw = _gw(provider)
    gw.call_json(Question, MSG)
    original_lock = gw._lock
    evicted = False

    class EvictionBeforeLock:
        def __enter__(self):
            nonlocal evicted
            original_lock.acquire()
            if not evicted:
                gw._cache.clear()
                evicted = True

        def __exit__(self, *_):
            original_lock.release()

    gw._lock = EvictionBeforeLock()
    assert gw.call_json(Question, MSG).text == GOOD["text"]
    assert len(provider.calls) == 2


def test_logs_latency_and_tokens(caplog):
    p = ScriptedProvider("a", [GOOD])
    with caplog.at_level(logging.INFO, logger="app.ai.gateway"):
        _gw(p).call_json(Question, MSG, session_id="s9")
    rec = next(r for r in caplog.records if getattr(r, "event", "") == "llm.call")
    assert rec.latency_ms >= 0 and rec.input_tokens == 100 and rec.output_tokens == 20
    assert rec.provider == "a" and rec.session_id == "s9" and rec.outcome == "ok"


# --- schema gửi nhà cung cấp ------------------------------------------------------------------


def test_provider_json_schema_strips_unsupported_keys():
    s = provider_json_schema(JudgeResult.model_json_schema())
    dumped = json.dumps(s)
    assert '"examples"' not in dumped and '"default"' not in dumped
    for sub in s["$defs"].values():
        for prop in sub.get("properties", {}).values():
            if "$ref" in prop:
                assert set(prop) == {"$ref"}
    assert s["properties"]["criteria"]["minItems"] == 5


# --- đổi nhà cung cấp chỉ bằng cấu hình -------------------------------------------------------


def test_fake_mode_uses_fake_provider():
    gw = build_gateway(Settings(llm_mode="fake"))
    assert isinstance(gw.primary, FakeProvider)
    assert len(gw.call_json(JudgeResult, MSG).criteria) == 5


def test_real_mode_gemini_with_openai_fallback():
    s = Settings(
        llm_mode="real",
        llm_provider="gemini",
        llm_model="gemini-2.5-flash",
        gemini_api_key="k",
        llm_fallback_provider="openai_compat",
        llm_fallback_model="gpt-x",
        openai_compat_base_url="http://llm.local/v1",
        openai_compat_api_key="k2",
    )
    gw = build_gateway(s)
    assert isinstance(gw.primary, GeminiProvider) and gw.primary.model == "gemini-2.5-flash"
    assert isinstance(gw.fallback, OpenAICompatProvider) and gw.fallback.model == "gpt-x"


def test_switch_primary_to_openai_compat_by_config():
    s = Settings(
        llm_mode="real",
        llm_provider="openai_compat",
        llm_model="qwen",
        openai_compat_base_url="http://llm.local/v1",
        llm_fallback_provider="gemini",
        llm_fallback_model="gemini-2.5-flash-lite",
        gemini_api_key="k",
    )
    gw = build_gateway(s)
    assert isinstance(gw.primary, OpenAICompatProvider) and isinstance(gw.fallback, GeminiProvider)


def test_fallback_same_provider_other_model():
    s = Settings(
        llm_mode="real", gemini_api_key="k", llm_fallback_provider="gemini", llm_fallback_model="gemini-2.0-flash"
    )
    gw = build_gateway(s)
    assert gw.fallback.model == "gemini-2.0-flash"


def test_missing_key_in_real_mode_is_config_error():
    with pytest.raises(AppError) as e:
        build_gateway(Settings(llm_mode="real", llm_provider="gemini", gemini_api_key=""))
    assert e.value.code == "LLM_NOT_CONFIGURED"


def test_unknown_provider_rejected():
    with pytest.raises(AppError) as e:
        build_gateway(Settings(llm_mode="real", llm_provider="khong-co"))
    assert e.value.code == "UNKNOWN_PROVIDER"


# --- OpenAICompatProvider (httpx.MockTransport) -----------------------------------------------


def _openai(handler) -> OpenAICompatProvider:
    return OpenAICompatProvider(
        "http://llm.local/v1", "sk-test", "gpt-x", http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )


def test_openai_compat_request_and_parse():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        seen["auth"] = req.headers["authorization"]
        seen["body"] = json.loads(req.content)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(GOOD)}}],
                "usage": {"prompt_tokens": 50, "completion_tokens": 7},
            },
        )

    r = _openai(handler).complete(MSG, Question.model_json_schema(), model="gpt-x")
    assert seen["url"] == "http://llm.local/v1/chat/completions" and seen["auth"] == "Bearer sk-test"
    assert seen["body"]["response_format"]["type"] == "json_schema"
    assert seen["body"]["response_format"]["json_schema"]["schema"]["properties"]["text"]
    assert seen["body"]["messages"] == MSG and seen["body"]["temperature"] == 0
    assert r.raw_text == json.dumps(GOOD) and (r.input_tokens, r.output_tokens) == (50, 7)


@pytest.mark.parametrize(
    ("status", "exc"),
    [
        (429, TransientProviderError),
        (503, TransientProviderError),
        (401, PermanentProviderError),
        (400, PermanentProviderError),
    ],
)
def test_openai_compat_error_mapping(status, exc):
    with pytest.raises(exc):
        _openai(lambda req: httpx.Response(status, json={"error": "x"})).complete(MSG, {}, model="gpt-x")


def test_openai_compat_timeout_is_transient():
    def handler(req):
        raise httpx.ReadTimeout("chậm", request=req)

    with pytest.raises(TransientProviderError):
        _openai(handler).complete(MSG, {}, model="gpt-x")


# --- GeminiProvider (client giả, không mạng) --------------------------------------------------


class _Usage:
    prompt_token_count = 40
    candidates_token_count = 9


class _Resp:
    text = json.dumps(GOOD)
    usage_metadata = _Usage()


class _Models:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.kwargs: dict[str, Any] = {}

    def generate_content(self, **kwargs):
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return _Resp()


class _Client:
    def __init__(self, error=None):
        self.models = _Models(error)


def test_gemini_builds_structured_output_request():
    client = _Client()
    msgs = MSG + [{"role": "assistant", "content": "{}"}, {"role": "user", "content": "sửa JSON"}]
    r = GeminiProvider("k", "gemini-2.5-flash", client=client).complete(
        msgs, Question.model_json_schema(), model="gemini-2.5-flash"
    )
    kw = client.models.kwargs
    cfg = kw["config"]
    assert kw["model"] == "gemini-2.5-flash"
    assert cfg.response_mime_type == "application/json"
    assert cfg.response_json_schema["properties"]["text"]
    assert cfg.system_instruction == "Bạn là Tutee" and cfg.temperature == 0
    assert [c["role"] for c in kw["contents"]] == ["user", "model", "user"]
    assert r.raw_text == json.dumps(GOOD) and (r.input_tokens, r.output_tokens) == (40, 9)


def test_gemini_error_mapping():
    from google.genai import errors

    with pytest.raises(TransientProviderError):
        GeminiProvider("k", "m", client=_Client(errors.ServerError(503, {"error": {"message": "quá tải"}}))).complete(
            MSG, {}, model="m"
        )
    with pytest.raises(TransientProviderError):
        GeminiProvider(
            "k", "m", client=_Client(errors.ClientError(429, {"error": {"message": "hết hạn mức"}}))
        ).complete(MSG, {}, model="m")
    with pytest.raises(PermanentProviderError):
        GeminiProvider("k", "m", client=_Client(errors.ClientError(400, {"error": {"message": "khóa sai"}}))).complete(
            MSG, {}, model="m"
        )
