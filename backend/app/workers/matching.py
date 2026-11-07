"""Hàng đợi `matching` – vòng ghép cặp và hết hạn gợi ý (Hình 4.14). Chủ: Long (C2-14).
Lịch beat ở `celery_app.py`: `scheduled_rounds` 06:00 hằng ngày, `expire_matches` mỗi 5 phút."""

import logging
from uuid import UUID

from app.core.errors import AppError
from app.db.session import SessionLocal
from app.services.live_matching import LiveMatching
from app.services.matching import MatchingService
from app.workers.celery_app import celery

log = logging.getLogger(__name__)


@celery.task(name="app.workers.matching.run_round")
def run_round(class_id: str, priority_node_id: str | None = None) -> dict | None:
    """Vòng định kỳ một lớp. Lớp không đủ SV (409) / chưa phát hành (404) ⇒ bỏ qua, ghi log."""
    db = SessionLocal()
    try:
        out = MatchingService(db).run_round(
            UUID(class_id), "SCHEDULED", None, UUID(priority_node_id) if priority_node_id else None
        )
        return {"roundId": str(out.id), "matches": len(out.matches)}
    except AppError as exc:
        db.rollback()
        if exc.code in ("NOT_ENOUGH_PARTICIPANTS", "TREE_NOT_PUBLISHED"):
            log.info("bỏ vòng ghép định kỳ lớp %s: %s", class_id, exc.code)
            return None
        raise
    finally:
        db.close()


@celery.task(name="app.workers.matching.scheduled_rounds")
def scheduled_rounds() -> list[str]:
    db = SessionLocal()
    try:
        ids = [str(c) for c in MatchingService(db).scheduled_class_ids()]
    finally:
        db.close()
    for cid in ids:
        run_round.delay(cid)
    return ids


@celery.task(name="app.workers.matching.live_rebalance")
def live_rebalance() -> int:
    """C2-15: mỗi phút ghép bạn đang chờ với người dạy còn chỗ ở các lớp có hạn kiểm tra đang mở. Trả số cặp mới."""
    db = SessionLocal()
    try:
        live = LiveMatching(db)
        return sum(live.rebalance_class(c) for c in live.open_class_ids())
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@celery.task(name="app.workers.matching.expire_matches")
def expire_matches() -> dict[str, int]:
    db = SessionLocal()
    try:
        return MatchingService(db).expire_due()
    finally:
        db.close()
