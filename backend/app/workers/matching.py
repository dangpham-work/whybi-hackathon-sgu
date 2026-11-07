"""Hàng đợi `matching` – vòng ghép cặp và hết hạn gợi ý (Hình 4.14). Chủ: Long (C2-14)."""

from app.workers.celery_app import celery


@celery.task(name="app.workers.matching.run_round")
def run_round(class_id: str, priority_node_id: str | None = None) -> None:
    raise NotImplementedError("C2-14")


@celery.task(name="app.workers.matching.scheduled_rounds")
def scheduled_rounds() -> None:
    raise NotImplementedError("C2-14")


@celery.task(name="app.workers.matching.expire_matches")
def expire_matches() -> None:
    raise NotImplementedError("C2-14")
