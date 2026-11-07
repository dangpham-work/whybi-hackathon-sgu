"""LLM Gateway – HỢP ĐỒNG DỮ LIỆU #3 (Bảng 7 kế hoạch): call_json(schema, messages) trả đối tượng
đúng schema; có cache, model dự phòng, thử lại khi lỗi parse, ngân sách token, LLM_MODE=fake.
Chủ: Đăng (C1-02) · Bên dùng: mọi tác tử và pipeline giáo trình.

Luồng một lời gọi:
  cache? → [provider chính → (lỗi tạm thời: thử lại có backoff) → JSON hỏng / sai schema: gửi lại kèm lỗi]
         → hết lượt / lỗi cố định ⇒ provider dự phòng (cùng quy trình) → hết ⇒ AppError 503 LLM_UNAVAILABLE.
Mỗi lượt gọi ghi log `llm.call` (provider, model, latency_ms, input/output_tokens, outcome, session_id).
"""

import hashlib
import json
import logging
import re
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any, Protocol, TypeVar
from uuid import uuid4

from pydantic import BaseModel, ValidationError
from redis import Redis
from redis.exceptions import RedisError

from app.ai.providers import PROVIDERS, build_provider
from app.ai.providers.base import LLMProvider, LLMResult, PermanentProviderError, ProviderError
from app.ai.providers.fake import FakeProvider
from app.core.config import Settings, get_settings
from app.core.errors import AppError

T = TypeVar("T", bound=BaseModel)
log = logging.getLogger("app.ai.gateway")

TOKEN_TTL_S = 7 * 24 * 60 * 60
REDIS_RETRY_S = 30

# Lưu mốc cộng bù cùng số đếm để thử lại an toàn khi mất phản hồi.
_TOKEN_INCREMENT = """
local previous = redis.call('GET', KEYS[2])
local delta = tonumber(ARGV[1])
if previous then
    delta = tonumber(ARGV[2]) - tonumber(previous)
end
local used = redis.call('INCRBY', KEYS[1], delta)
redis.call('EXPIRE', KEYS[1], ARGV[3])
redis.call('SET', KEYS[2], ARGV[2], 'EX', ARGV[3])
return used
"""

_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.S)


class TokenStore(Protocol):
    def get(self, session_id: str) -> int: ...

    def increment(self, session_id: str, amount: int) -> int: ...


class InMemoryTokenStore:
    def __init__(self):
        self._tokens: dict[str, int] = {}
        self._lock = threading.Lock()

    def get(self, session_id: str) -> int:
        with self._lock:
            return self._tokens.get(session_id, 0)

    def increment(self, session_id: str, amount: int) -> int:
        with self._lock:
            used = self._tokens.get(session_id, 0) + amount
            self._tokens[session_id] = used
            return used


class RedisTokenStore:
    """Đếm chung qua Redis; tạm dùng RAM khi lỗi và cộng bù khi nối lại."""

    def __init__(self, client: Redis, ttl_s: int, *, clock: Callable[[], float] | None = None):
        self._client = client
        self._ttl_s = ttl_s
        self._clock = clock if clock is not None else time.monotonic
        self._tokens: dict[str, int] = {}
        self._pending: dict[str, int] = {}
        self._synced: dict[str, int] = {}
        self._worker_id = uuid4().hex
        self._lock = threading.Lock()
        self._retry_at = 0.0

    def get(self, session_id: str) -> int:
        return self._access(session_id)

    def increment(self, session_id: str, amount: int) -> int:
        return self._access(session_id, amount)

    def _access(self, session_id: str, amount: int | None = None) -> int:
        key = f"llm:tokens:{session_id}"
        with self._lock:
            if amount is not None:
                self._tokens[session_id] = self._tokens.get(session_id, 0) + amount
                self._pending[session_id] = self._pending.get(session_id, 0) + amount
            if self._clock() >= self._retry_at:
                try:
                    for pending_session, delta in list(self._pending.items()):
                        pending_key = f"llm:tokens:{pending_session}"
                        synced = self._synced.get(pending_session, 0) + delta
                        self._tokens[pending_session] = int(
                            self._client.eval(
                                _TOKEN_INCREMENT,
                                2,
                                pending_key,
                                f"llm:token-sync:{self._worker_id}:{pending_session}",
                                delta,
                                synced,
                                self._ttl_s,
                            )
                        )
                        self._synced[pending_session] = synced
                        del self._pending[pending_session]
                    if amount is None:
                        self._tokens[session_id] = int(self._client.get(key) or 0)
                except (RedisError, OSError) as error:
                    self._retry_at = self._clock() + REDIS_RETRY_S
                    # Chỉ log loại lỗi để tránh lộ thông tin kết nối.
                    log.warning(
                        "llm.token_store_fallback: Redis unavailable (%s); using in-memory token counts",
                        type(error).__name__,
                        extra={"event": "llm.token_store_fallback"},
                    )
            return self._tokens.get(session_id, 0)

    def close(self) -> None:
        self._client.close()


class _InvalidOutput(Exception):
    def __init__(self, reason: str, raw: str):
        super().__init__(reason)
        self.reason = reason
        self.raw = raw


def _parse(result: LLMResult) -> Any:
    if result.data is not None:
        return result.data
    text = result.raw_text.strip()
    m = _FENCE.match(text)
    if m:
        text = m.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise _InvalidOutput(f"JSON không hợp lệ: {e.msg} (vị trí {e.pos})", result.raw_text) from e


def _feedback(messages: list[dict[str, str]], err: _InvalidOutput) -> list[dict[str, str]]:
    """UC06 luồng 4a: gửi lại kèm lỗi để model tự sửa; giữ nguyên prompt gốc."""
    return [
        *messages,
        {"role": "assistant", "content": err.raw[:4000]},
        {
            "role": "user",
            "content": f"Đầu ra trước không dùng được – {err.reason}. "
            "Chỉ trả về MỘT đối tượng JSON đúng schema đã cho, không kèm giải thích.",
        },
    ]


class LLMGateway:
    def __init__(
        self,
        primary: LLMProvider,
        fallback: LLMProvider | None = None,
        max_retries: int = 2,
        *,
        transient_retries: int = 1,
        cache_size: int = 256,
        token_budget: int = 20_000,
        backoff_s: float = 0.5,
        sleep: Callable[[float], None] = time.sleep,
        token_store: TokenStore | None = None,
    ):
        self.primary = primary
        self.fallback = fallback
        self.max_retries = max_retries
        self.transient_retries = transient_retries
        self.cache_size = cache_size
        self.token_budget = token_budget
        self.backoff_s = backoff_s
        self._sleep = sleep
        self._cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._token_store = token_store if token_store is not None else InMemoryTokenStore()
        self._budget_exceeded: set[str] = set()
        self._lock = threading.Lock()

    def close(self) -> None:
        """Đóng kết nối HTTP của các provider (khi đổi cấu hình)."""
        for p in (self.primary, self.fallback, self._token_store):
            close = getattr(p, "close", None)
            if close is not None:
                try:
                    close()
                except Exception:  # noqa: BLE001 – đóng hỏng không được làm hỏng việc đổi cấu hình
                    log.warning("Không đóng được provider %s", getattr(p, "name", p))

    # --- ngân sách token theo phiên (NFR-13) ---

    def tokens_used(self, session_id: str) -> int:
        return self._token_store.get(str(session_id))

    def _check_budget(self, session_id: str | None) -> None:
        if session_id is None or not self.token_budget:
            return
        used = self.tokens_used(session_id)
        if used >= self.token_budget:
            self._budget_exceeded.add(str(session_id))
            raise AppError(
                429,
                "TOKEN_BUDGET_EXCEEDED",
                "Phiên đã dùng hết ngân sách token",
                {"sessionId": str(session_id), "used": used, "budget": self.token_budget},
            )
        self._budget_exceeded.discard(str(session_id))

    def has_exceeded_budget(self, session_id: str) -> bool:
        return str(session_id) in self._budget_exceeded

    def _charge(self, session_id: str | None, result: LLMResult) -> None:
        if session_id is not None:
            self._token_store.increment(str(session_id), result.input_tokens + result.output_tokens)

    # --- cache ---

    def _cache_key(self, schema: type[BaseModel], messages, model, temperature) -> str:
        raw = json.dumps(
            [schema.__module__, schema.__qualname__, messages, model, temperature], ensure_ascii=False, sort_keys=True
        )
        return hashlib.sha256(raw.encode()).hexdigest()

    # --- gọi ---

    def call_json(
        self,
        schema: type[T],
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0,
        session_id: str | None = None,
        use_cache: bool = True,
    ) -> T:
        """Gọi LLM, ép JSON theo `schema`, trả về instance đã validate.

        `model` ghi đè model của provider chính (vd. Guard dùng LLM_GUARD_MODEL); provider dự phòng dùng model
        của nó. `session_id` bật ngân sách token phiên. Cache chỉ áp khi temperature = 0.
        """
        self._check_budget(session_id)
        cacheable = use_cache and self.cache_size > 0 and temperature == 0
        key = self._cache_key(schema, messages, model or self.primary.model, temperature) if cacheable else ""
        if cacheable:
            with self._lock:
                data = self._cache.get(key)
                if data is not None:
                    self._cache.move_to_end(key)
            if data is not None:
                log.info("llm.cache_hit", extra={"event": "llm.cache_hit", "session_id": session_id})
                return schema.model_validate(data)

        json_schema = schema.model_json_schema()
        targets: list[tuple[LLMProvider, str]] = [(self.primary, model or self.primary.model)]
        if self.fallback is not None:
            targets.append((self.fallback, self.fallback.model))

        errors: list[dict[str, str]] = []
        for provider, target_model in targets:
            try:
                obj = self._call_provider(
                    provider, target_model, schema, json_schema, messages, temperature, session_id
                )
            except (ProviderError, _InvalidOutput) as e:
                # chi tiết lỗi chỉ ghi log; client chỉ thấy provider/model và loại lỗi
                log.warning("llm.target_failed %s/%s: %s", provider.name, target_model, e)
                errors.append({"provider": provider.name, "model": target_model, "error": type(e).__name__})
                continue
            if cacheable:
                with self._lock:
                    self._cache[key] = obj.model_dump(mode="json")
                    while len(self._cache) > self.cache_size:
                        self._cache.popitem(last=False)
            return obj

        raise AppError(503, "LLM_UNAVAILABLE", "Dịch vụ AI tạm thời không khả dụng", {"attempts": errors})

    def _call_provider(self, provider, model, schema: type[T], json_schema, messages, temperature, session_id) -> T:
        msgs = messages
        last: _InvalidOutput | None = None
        for attempt in range(1 + self.max_retries):
            result = self._complete_with_retry(provider, model, msgs, json_schema, temperature, session_id, attempt)
            self._charge(session_id, result)
            try:
                obj = schema.model_validate(_parse(result))
            except _InvalidOutput as e:
                last = e
            except ValidationError as e:
                last = _InvalidOutput(
                    f"sai schema: {e.errors(include_url=False, include_input=False)}",
                    result.raw_text or json.dumps(result.data, ensure_ascii=False),
                )
            else:
                self._log(provider, model, result, "ok", attempt, session_id)
                return obj
            self._log(provider, model, result, "invalid_output", attempt, session_id, level=logging.WARNING)
            msgs = _feedback(messages, last)
        assert last is not None
        raise last

    def _complete_with_retry(self, provider, model, msgs, json_schema, temperature, session_id, attempt) -> LLMResult:
        for i in range(1 + self.transient_retries):
            self._check_budget(session_id)
            t0 = time.perf_counter()
            try:
                result = provider.complete(msgs, json_schema, model=model, temperature=temperature)
            except PermanentProviderError as e:
                self._log_error(provider, model, e, t0, attempt, session_id)
                raise
            except ProviderError as e:
                self._log_error(provider, model, e, t0, attempt, session_id)
                if i == self.transient_retries:
                    raise
                self._sleep(self.backoff_s * (2**i))
                continue
            if not result.latency_ms:
                result.latency_ms = int((time.perf_counter() - t0) * 1000)
            return result
        raise AssertionError("unreachable")

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embedding cho gộp trùng / tiên quyết (C1-10) và RAG (C1-11): provider chính, hỏng thì dự phòng."""
        errors: list[str] = []
        for provider in (self.primary, self.fallback):
            if provider is None:
                continue
            try:
                return provider.embed(texts)
            except ProviderError as e:
                errors.append(f"{getattr(provider, 'name', '?')}: {e}")
        raise AppError(503, "LLM_UNAVAILABLE", "Dịch vụ AI tạm thời không khả dụng", {"attempts": errors})

    # --- log (NFR: latency mỗi lượt) ---

    def _log(self, provider, model, result: LLMResult, outcome, attempt, session_id, level=logging.INFO) -> None:
        log.log(
            level,
            "llm.call %s/%s %s %dms",
            provider.name,
            model,
            outcome,
            result.latency_ms,
            extra={
                "event": "llm.call",
                "provider": provider.name,
                "model": model,
                "outcome": outcome,
                "attempt": attempt,
                "latency_ms": result.latency_ms,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "session_id": session_id,
            },
        )

    def _log_error(self, provider, model, err: Exception, t0: float, attempt, session_id) -> None:
        log.warning(
            "llm.call %s/%s error: %s",
            provider.name,
            model,
            type(err).__name__,
            extra={
                "event": "llm.call",
                "provider": provider.name,
                "model": model,
                "outcome": "error",
                "attempt": attempt,
                "latency_ms": int((time.perf_counter() - t0) * 1000),
                "session_id": session_id,
            },
        )


# --- dựng gateway từ cấu hình -----------------------------------------------------------------

_override: dict[str, str | None] = {}  # PUT /admin/ai-config ghi đè khi chạy (C2-06 sẽ lưu CSDL)


def build_gateway(settings: Settings, override: dict[str, str | None] | None = None) -> LLMGateway:
    """Đổi nhà cung cấp = đổi cấu hình (LLM_PROVIDER, LLM_MODEL, LLM_FALLBACK_*), không sửa nghiệp vụ."""
    o = override or {}
    common = dict(
        max_retries=settings.llm_max_retries,
        transient_retries=settings.llm_transient_retries,
        cache_size=settings.llm_cache_size,
        token_budget=settings.llm_session_token_budget,
    )
    if settings.llm_mode == "fake":
        return LLMGateway(FakeProvider(), **common)

    primary = build_provider(o.get("provider") or settings.llm_provider, o.get("model") or settings.llm_model, settings)
    fb_name = o["fallback_provider"] if "fallback_provider" in o else settings.llm_fallback_provider
    fb_model = o["fallback_model"] if "fallback_model" in o else settings.llm_fallback_model
    fallback = None
    if fb_name and fb_model:
        try:
            fallback = build_provider(fb_name, fb_model, settings)
        except AppError as e:
            if e.code != "LLM_NOT_CONFIGURED":
                raise
            log.warning("Bỏ qua model dự phòng %s/%s: %s", fb_name, fb_model, e.message)
    token_store = None
    if settings.app_env != "test" and settings.redis_url:
        token_store = RedisTokenStore(
            Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=1),
            TOKEN_TTL_S,
        )
    return LLMGateway(primary, fallback, token_store=token_store, **common)


_current: LLMGateway | None = None
_build_lock = threading.Lock()


def get_gateway() -> LLMGateway:
    global _current
    if _current is None:
        with _build_lock:
            if _current is None:
                _current = build_gateway(get_settings(), _override)
    return _current


def _swap(new_gw: LLMGateway | None) -> None:
    global _current
    with _build_lock:
        old, _current = _current, new_gw
    if old is not None:
        old.close()


def configure_llm(
    provider: str, model: str, fallback_provider: str | None = None, fallback_model: str | None = None
) -> LLMGateway:
    """Áp cấu hình LLM mới lúc chạy (PUT /admin/ai-config). Dựng thử trước – cấu hình sai thì giữ cấu hình cũ."""
    for name in (provider, fallback_provider):
        if name and name not in PROVIDERS:
            raise AppError(422, "UNKNOWN_PROVIDER", f"Nhà cung cấp LLM không hỗ trợ: {name}", {"allowed": PROVIDERS})
    new = {
        "provider": provider,
        "model": model,
        "fallback_provider": fallback_provider,
        "fallback_model": fallback_model,
    }
    gw = build_gateway(get_settings(), new)
    _override.clear()
    _override.update(new)
    _swap(gw)  # đóng kết nối của gateway cũ
    return gw


def reset_gateway() -> None:
    """Bỏ ghi đè và dựng lại gateway từ biến môi trường (dùng trong test)."""
    _override.clear()
    _swap(None)
