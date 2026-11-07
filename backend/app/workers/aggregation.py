"""Hàng đợi `aggregation` – tổng hợp bản đồ nhiệt khi có mastery.changed (Hình 4.13). Chủ: Long (C2-11, C2-17)."""

from app.workers.celery_app import celery


@celery.task(name="app.workers.aggregation.recompute_node")
def recompute_node(class_id: str, node_id: str) -> None:
    raise NotImplementedError("C2-11")


@celery.task(name="app.workers.aggregation.purge_expired_audio")
def purge_expired_audio() -> None:
    raise NotImplementedError("C2-17")
