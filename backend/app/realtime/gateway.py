"""RealtimeGateway – phát payload ra kênh WebSocket (Bảng 5.11). Chủ: Long (C2-13).

Đường đi của một tin (MT5: GV thấy ô đổi màu ≤ 3 giây):

    worker aggregation (Celery) ── broadcast(channel, event, payload) ──▶ Redis kênh "ws:<channel>"
    tiến trình api: RedisRelay (luồng nền, psubscribe "ws:*") ──▶ Hub ──▶ hàng đợi từng kết nối ──▶ WebSocket

- Tin trên dây và gửi cho trình duyệt: `{"channel", "event", "payload"}` (camelCase) – khớp `frontend/src/lib/ws.ts`.
- `APP_ENV=test` hoặc `EVENT_BUS=memory`: không qua Redis, `broadcast` giao thẳng cho `hub` của tiến trình
  (một tiến trình – test, dev không Redis).
- Pub/Sub không lưu tin: trình duyệt nối lại thì tải lại ảnh chụp GET /classes/{id}/heatmap (ws.ts phát "reconnected").
"""

import asyncio
import json
import logging
import threading
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from pydantic import BaseModel

from app.core.config import get_settings

log = logging.getLogger(__name__)

REDIS_PREFIX = "ws:"
QUEUE_LIMIT = 1000  # tin chờ gửi tối đa mỗi kết nối – trình duyệt treo thì bỏ tin, không giữ bộ nhớ mãi

EVENT_HEATMAP_CELL = "heatmap.cell"
EVENT_HEATMAP_NODE = "heatmap.node"
EVENT_HEATMAP_ALERT = "heatmap.alert"


def channel_heatmap(class_id: Any) -> str:
    return f"class:{class_id}:heatmap"


def channel_job(job_id: Any) -> str:
    return f"job:{job_id}"


def channel_user(user_id: Any) -> str:
    return f"user:{user_id}"


def channel_session(session_id: Any) -> str:
    return f"session:{session_id}"


def encode(channel: str, event: str, payload: BaseModel | dict[str, Any] | None) -> str:
    if isinstance(payload, BaseModel):
        body: Any = payload.model_dump(mode="json", by_alias=True)
    else:
        body = payload
    return json.dumps({"channel": channel, "event": event, "payload": body}, ensure_ascii=False)


@dataclass(eq=False)
class Connection:
    """Một kết nối WebSocket trong tiến trình api: tin đến từ luồng khác được đẩy vào hàng đợi của vòng lặp sự kiện."""

    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(QUEUE_LIMIT))
    dropped: int = 0

    def _put(self, message: str) -> None:
        try:
            self.queue.put_nowait(message)
        except asyncio.QueueFull:
            self.dropped += 1
            if self.dropped == 1 or self.dropped % 100 == 0:
                log.warning("kết nối WebSocket chậm, đã bỏ %d tin", self.dropped)

    def push(self, message: str) -> None:
        """An toàn khi gọi từ luồng bất kỳ."""
        try:
            self.loop.call_soon_threadsafe(self._put, message)
        except RuntimeError:  # vòng lặp đã đóng – kết nối đang hủy
            pass


class Hub:
    """Đăng ký kênh → các kết nối đang nghe, trong MỘT tiến trình api."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._channels: dict[str, set[Connection]] = {}

    def subscribe(self, channel: str, conn: Connection) -> None:
        with self._lock:
            self._channels.setdefault(channel, set()).add(conn)

    def unsubscribe(self, channel: str, conn: Connection) -> None:
        with self._lock:
            conns = self._channels.get(channel)
            if conns is not None:
                conns.discard(conn)
                if not conns:
                    del self._channels[channel]

    def drop(self, conn: Connection) -> None:
        with self._lock:
            for channel in [c for c, conns in self._channels.items() if conn in conns]:
                self._channels[channel].discard(conn)
                if not self._channels[channel]:
                    del self._channels[channel]

    def listeners(self, channel: str) -> int:
        with self._lock:
            return len(self._channels.get(channel, ()))

    def deliver(self, channel: str, message: str) -> int:
        """Giao một tin đã mã hóa cho mọi kết nối của kênh. Trả số kết nối nhận."""
        with self._lock:
            conns = list(self._channels.get(channel, ()))
        for conn in conns:
            conn.push(message)
        return len(conns)


hub = Hub()


class RedisRelay:
    """Luồng nền trong tiến trình api: nghe "ws:*" trên Redis và giao cho `hub`. Khởi động lười khi có kết nối đầu."""

    def __init__(self, redis_url: str | None = None, client: Any = None, target: Hub | None = None) -> None:
        if client is None:
            import redis

            client = redis.Redis.from_url(redis_url or get_settings().redis_url, decode_responses=True)
        self._client = client
        self._hub = target or hub
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def _run(self, ready: threading.Event) -> None:
        while not self._stop.is_set():
            pubsub = self._client.pubsub(ignore_subscribe_messages=True)
            try:
                pubsub.psubscribe(f"{REDIS_PREFIX}*")
                ready.set()
                while not self._stop.is_set():
                    msg = pubsub.get_message(timeout=1.0)
                    if not msg or msg.get("type") != "pmessage":
                        continue
                    channel = msg["channel"]
                    data = msg["data"]
                    if isinstance(channel, bytes):
                        channel = channel.decode()
                    if isinstance(data, bytes):
                        data = data.decode()
                    self._hub.deliver(channel.removeprefix(REDIS_PREFIX), data)
            except Exception:
                # Redis rớt: ghi log rồi nối lại sau 1 giây; trình duyệt tải lại ảnh chụp khi cần.
                log.exception("RedisRelay mất kết nối Redis – thử nối lại")
                self._stop.wait(1.0)
            finally:
                try:
                    pubsub.close()
                except Exception:  # pragma: no cover - đóng kết nối đã hỏng
                    pass

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            ready = threading.Event()
            self._thread = threading.Thread(target=self._run, args=(ready,), name="ws-relay", daemon=True)
            self._thread.start()
        ready.wait(5)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(5)


def _in_process() -> bool:
    s = get_settings()
    return s.app_env == "test" or s.event_bus == "memory"


@lru_cache
def get_relay() -> RedisRelay | None:
    """None khi chạy một tiến trình (test / EVENT_BUS=memory) – `broadcast` đã giao thẳng cho `hub`."""
    return None if _in_process() else RedisRelay()


def ensure_relay() -> None:
    relay = get_relay()
    if relay is not None:
        relay.start()


@lru_cache
def _redis() -> Any:
    import redis

    return redis.Redis.from_url(get_settings().redis_url, decode_responses=True)


def broadcast(channel: str, event: str, payload: BaseModel | dict[str, Any] | None) -> None:
    """Phát một sự kiện ra kênh WebSocket (gọi từ worker hoặc api, đồng bộ). Lỗi Redis ném cho bên gọi."""
    message = encode(channel, event, payload)
    if _in_process():
        hub.deliver(channel, message)
    else:
        _redis().publish(REDIS_PREFIX + channel, message)
