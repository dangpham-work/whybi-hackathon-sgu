"""Tiến trình nghe `session.completed` → MasteryService.apply_result → `mastery.changed` (C2-10)
và → MatchingService.verify_from_session (C2-14). Chủ: Long.
C2-11: cùng tiến trình nghe `mastery.changed` → đẩy tính lại bản đồ nhiệt vào hàng đợi `aggregation`.

Chạy: `python -m app.workers.mastery_listener` (dịch vụ `events` trong docker-compose).
Chỉ chạy MỘT tiến trình: Redis Pub/Sub phát cho mọi bên nghe; apply_result chịu được tin lặp nhưng không cần nhân bản.
"""

import logging

from app.realtime.bus import EventBus, RedisEventBus, get_bus
from app.services import heatmap
from app.services.mastery import register_handlers
from app.services.matching import register_handlers as register_matching_handlers

log = logging.getLogger(__name__)


def main(bus: EventBus | None = None) -> None:
    bus = bus or get_bus()
    register_handlers(bus)
    heatmap.register_handlers(bus)
    register_matching_handlers(bus)  # C2-14: xác nhận lại sau học cặp
    if not isinstance(bus, RedisEventBus):
        raise SystemExit("mastery_listener cần Redis (EVENT_BUS khác 'memory', APP_ENV khác 'test')")
    log.info("mastery_listener: đang nghe session.completed, mastery.changed")
    bus.listen()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
