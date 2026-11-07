"""Hàng đợi `aggregation` – tổng hợp bản đồ nhiệt khi có mastery.changed (Hình 4.13). Chủ: Long (C2-11, C2-17).

Ai đẩy việc: `app.services.heatmap.register_handlers` (chạy trong tiến trình `mastery_listener`).
Mọi task tính lại từ CSDL nên chạy lặp / sai thứ tự vẫn cho cùng kết quả (idempotent).
C2-12: tính lại xong thì truy vết điểm nghẽn gốc cả lớp (`trace_root_causes`) trong cùng giao dịch – một nút đổi
có thể đổi r(X|Y) của mọi nút con cháu. Cảnh báo trả về để C2-13 đẩy `heatmap.alert`.
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
    from app.services.heatmap import HeatmapService, push_updates

    db = _session()
    try:
        svc = HeatmapService(db)
        node = svc.recompute(UUID(class_id), UUID(node_id))
        alerts = [] if node is None else svc.trace_root_causes(UUID(class_id))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    if node is None:
        return None
    push_updates(UUID(class_id), [node], alerts)  # sau commit: GV tải lại ảnh chụp cũng thấy đúng số này
    return node.model_dump(mode="json", by_alias=True)


@celery.task(name="app.workers.aggregation.recompute_class")
def recompute_class(class_id: str) -> int:
    """Tính lại mọi nút của bản đang phát hành. Trả số nút đã ghi."""
    from app.services.heatmap import HeatmapService, push_updates

    db = _session()
    try:
        svc = HeatmapService(db)
        nodes = svc.recompute_class(UUID(class_id))
        alerts = svc.trace_root_causes(UUID(class_id))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    push_updates(UUID(class_id), nodes, alerts)  # đối soát cũng đẩy lên màn GV đang mở
    return len(nodes)


@celery.task(name="app.workers.aggregation.push_cell")
def push_cell(event_json: str) -> dict:
    """C2-13: một mastery.changed → heatmap.cell (kèm tên, MSSV) trên class:{id}:heatmap. Chỉ đọc CSDL."""
    from app.models.schemas.mastery import MasteryChanged
    from app.services import heatmap

    event = MasteryChanged.model_validate_json(event_json)
    db = _session()
    try:
        cell = heatmap.HeatmapService(db).cell(event)
    finally:
        db.close()
    heatmap.push_cell(event.class_id, cell)
    return cell.model_dump(mode="json", by_alias=True)


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
