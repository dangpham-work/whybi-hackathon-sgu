"""Hàng đợi `aggregation` – tổng hợp bản đồ nhiệt khi có mastery.changed (Hình 4.13). Chủ: Long (C2-11, C2-17).

Ai đẩy việc: `app.services.heatmap.register_handlers` (chạy trong tiến trình `mastery_listener`).
Mọi task tính lại từ CSDL nên chạy lặp / sai thứ tự vẫn cho cùng kết quả (idempotent).
"""

import logging
from uuid import UUID

from app.workers.celery_app import celery

log = logging.getLogger(__name__)


def _session():
    from app.db.session import SessionLocal

    return SessionLocal()


@celery.task(name="app.workers.aggregation.recompute_node")
def recompute_node(class_id: str, node_id: str) -> dict | None:
    """Tính lại một nút (6.5.1: chỉ tính nút bị ảnh hưởng) và ghi class_node_stats. Trả payload heatmap.node."""
    from app.services.heatmap import HeatmapService

    db = _session()
    try:
        node = HeatmapService(db).recompute(UUID(class_id), UUID(node_id))
        db.commit()
        return None if node is None else node.model_dump(mode="json", by_alias=True)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@celery.task(name="app.workers.aggregation.recompute_class")
def recompute_class(class_id: str) -> int:
    """Tính lại mọi nút của bản đang phát hành. Trả số nút đã ghi."""
    from app.services.heatmap import HeatmapService

    db = _session()
    try:
        n = len(HeatmapService(db).recompute_class(UUID(class_id)))
        db.commit()
        return n
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@celery.task(name="app.workers.aggregation.reconcile_all")
def reconcile_all() -> int:
    """Đối soát định kỳ (beat): Pub/Sub không lưu tin – sự kiện mất thì ô vẫn đúng sau ≤ 1 chu kỳ."""
    from app.services.heatmap import HeatmapService

    db = _session()
    try:
        class_ids = HeatmapService(db).published_class_ids()
    finally:
        db.close()
    for cid in class_ids:
        recompute_class.delay(str(cid))
    log.info("reconcile_all: đã đẩy %d lớp", len(class_ids))
    return len(class_ids)


@celery.task(name="app.workers.aggregation.purge_expired_audio")
def purge_expired_audio() -> None:
    raise NotImplementedError("C2-17")
