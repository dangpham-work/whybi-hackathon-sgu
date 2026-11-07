"""Celery – 4 hàng đợi theo Bảng 5.15 (documents, aggregation, matching, ai) + lịch beat.
Chủ: Long (C2-03); task documents: Đăng (C1-09)."""

from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

celery = Celery(
    "whybi",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.documents", "app.workers.aggregation", "app.workers.matching"],
)
app = celery  # để `celery -A app.workers.celery_app` tìm thấy

celery.conf.update(
    task_default_queue="ai",
    task_routes={
        "app.workers.documents.*": {"queue": "documents"},
        "app.workers.aggregation.*": {"queue": "aggregation"},
        "app.workers.matching.*": {"queue": "matching"},
    },
    timezone="Asia/Ho_Chi_Minh",
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        # FR-PM-02: ghép cặp định kỳ – C2-14
        "matching-daily": {"task": "app.workers.matching.scheduled_rounds", "schedule": crontab(hour=6, minute=0)},
        # BR-09: gợi ý quá 48 giờ / xác nhận quá 7 ngày – C2-14
        "expire-matches": {"task": "app.workers.matching.expire_matches", "schedule": 300.0},
        # NFR-09: dọn ghi âm quá hạn (mặc định 30 ngày) – C2-17
        "purge-audio": {"task": "app.workers.aggregation.purge_expired_audio", "schedule": crontab(hour=3, minute=0)},
    },
)
