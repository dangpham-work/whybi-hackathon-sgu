"""EventBus – Redis Pub/Sub (Observer, Hình 5.11). Chủ: Long (C2-05).
Chủ đề: session.completed, mastery.changed (app/models/schemas/mastery.py)."""

from collections.abc import Callable
from typing import Any


class RedisEventBus:
    def __init__(self, redis_url: str):
        self.redis_url = redis_url

    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        raise NotImplementedError("C2-05")

    def subscribe(self, topic: str, handler: Callable[[dict[str, Any]], None]) -> None:
        raise NotImplementedError("C2-05")
