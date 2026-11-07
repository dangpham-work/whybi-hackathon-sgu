"""EventBus – Redis Pub/Sub (Observer, Hình 5.11, mục 5.1.3). Chủ: Long (C2-05).

Chủ đề và payload (đã chốt):
- `session.completed` → `SessionResult` (Đăng phát sau khi Judge chấm; MasteryService nghe, C2-10).
- `mastery.changed` → `MasteryChanged` (chỉ MasteryService phát; heatmap C2-11, matching C2-14 nghe).

Trên dây: JSON camelCase (`model_dump_json(by_alias=True)`), kênh Redis trùng tên chủ đề.
Handler luôn nhận model Pydantic đã kiểm, không nhận dict thô.

    bus = get_bus()
    bus.subscribe(TOPIC_SESSION_COMPLETED, mastery_service.apply_result)   # khi khởi động worker
    bus.publish(TOPIC_SESSION_COMPLETED, session_result)                   # bên phát

Redis: `publish` gửi ngay; handler chỉ chạy trong tiến trình đã gọi `listen()` (hoặc `start()` – luồng nền).
Pub/Sub không lưu tin: bên nghe chưa chạy thì mất sự kiện. Cần bền thì C2-10 ghi kết quả vào CSDL trước khi phát.
"""

import logging
import threading
from collections import defaultdict
from collections.abc import Callable
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.models.schemas.mastery import TOPIC_MASTERY_CHANGED, TOPIC_SESSION_COMPLETED, MasteryChanged
from app.models.schemas.session import SessionResult

log = logging.getLogger(__name__)

TOPICS: dict[str, type[BaseModel]] = {
    TOPIC_SESSION_COMPLETED: SessionResult,
    TOPIC_MASTERY_CHANGED: MasteryChanged,
}

Handler = Callable[[Any], None]


class UnknownTopic(KeyError):
    pass


def _schema(topic: str) -> type[BaseModel]:
    try:
        return TOPICS[topic]
    except KeyError:
        raise UnknownTopic(topic) from None


def encode(topic: str, event: BaseModel) -> str:
    schema = _schema(topic)
    if not isinstance(event, schema):
        raise TypeError(f"{topic} cần payload {schema.__name__}, nhận {type(event).__name__}")
    return event.model_dump_json(by_alias=True)


def decode(topic: str, data: str | bytes) -> BaseModel:
    return _schema(topic).model_validate_json(data)


class EventBus:
    """Phần chung: đăng ký handler và phát cho handler sau khi giải mã, kiểm schema."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, topic: str, handler: Handler) -> None:
        _schema(topic)
        self._handlers[topic].append(handler)

    def publish(self, topic: str, event: BaseModel) -> None:
        raise NotImplementedError

    def dispatch(self, topic: str, data: str | bytes) -> None:
        """Giải mã một tin nhận được và gọi mọi handler của chủ đề. Tin hỏng hoặc handler lỗi chỉ ghi log."""
        try:
            event = decode(topic, data)
        except (ValidationError, UnknownTopic) as exc:
            log.error("bỏ tin hỏng trên %s: %s", topic, exc)
            return
        for handler in list(self._handlers.get(topic, [])):
            try:
                handler(event)
            except Exception:
                log.exception("handler %r lỗi khi xử lý %s", handler, topic)


class InMemoryEventBus(EventBus):
    """Một tiến trình, đồng bộ – dùng cho test và dev không Redis. Vẫn đi qua encode/decode như Redis."""

    def publish(self, topic: str, event: BaseModel) -> None:
        self.dispatch(topic, encode(topic, event))


class RedisEventBus(EventBus):
    def __init__(self, redis_url: str | None = None, client: Any = None) -> None:
        super().__init__()
        if client is None:
            import redis

            client = redis.Redis.from_url(redis_url or get_settings().redis_url, decode_responses=True)
        self._client = client
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def publish(self, topic: str, event: BaseModel) -> None:
        self._client.publish(topic, encode(topic, event))

    def listen(
        self, stop: threading.Event | None = None, timeout: float = 1.0, ready: threading.Event | None = None
    ) -> None:
        """Vòng nghe chặn: nhận tin của mọi chủ đề đã `subscribe` tới khi `stop` được đặt."""
        stop = stop or self._stop
        topics = list(self._handlers)
        if not topics:
            raise RuntimeError("chưa subscribe chủ đề nào")
        pubsub = self._client.pubsub(ignore_subscribe_messages=True)
        pubsub.subscribe(*topics)
        if ready is not None:
            ready.set()
        try:
            while not stop.is_set():
                msg = pubsub.get_message(timeout=timeout)
                if msg and msg.get("type") == "message":
                    channel = msg["channel"]
                    if isinstance(channel, bytes):
                        channel = channel.decode()
                    self.dispatch(channel, msg["data"])
        finally:
            pubsub.close()

    def start(self) -> threading.Thread:
        """Chạy `listen()` trong luồng nền (worker, startup của api). Gọi sau mọi `subscribe`."""
        ready = threading.Event()
        self._thread = threading.Thread(target=self.listen, kwargs={"ready": ready}, name="event-bus", daemon=True)
        self._thread.start()
        ready.wait(5)
        return self._thread

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(5)


@lru_cache
def get_bus() -> EventBus:
    s = get_settings()
    if s.app_env == "test" or s.event_bus == "memory":
        return InMemoryEventBus()
    return RedisEventBus(s.redis_url)
