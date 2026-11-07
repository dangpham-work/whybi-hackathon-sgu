"""HeatmapService – HeatmapAggregator: tính chỉ số nút, phân màu BR-06, truy vết gốc, đẩy WebSocket (mục 6.5).
Chủ: Long (C2-11…C2-13).

C2-11 (đã làm):
- `mastery.changed` → `register_handlers` đẩy (class_id, node_id) vào hàng đợi `aggregation`
  (`app.workers.aggregation.recompute_node`). Bỏ qua lý do không đổi số liệu (bắt đầu / bỏ dở phiên, mở khóa).
- `recompute(class_id, node_id)` đọc cột ma trận qua `MasteryService.columns` (không truy vấn thẳng mastery_records),
  tính chỉ số + màu bằng `app.algorithms.heatmap`, ghi đè dòng `class_node_stats` (upsert, idempotent),
  trả `HeatmapNode` (kèm `nodeKey`, `label`) cho C2-13 đẩy lên kênh class:{id}:heatmap.
- `recompute_class(class_id)` tính lại mọi nút – dùng khi đối soát định kỳ (bù sự kiện Pub/Sub bị mất).
Không ghi `root_cause_*` (C2-12) và `top_misconceptions` (C2-13 chi tiết nút).
"""

import logging
from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING
from uuid import UUID

from kombu.exceptions import OperationalError as KombuOperationalError
from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.algorithms.heatmap import ColorRule, NodeStat, aggregate, classify, label
from app.db.base import utcnow
from app.models.enums import MasteryChangeReason
from app.models.peer import ClassNodeStat
from app.models.schemas.mastery import TOPIC_MASTERY_CHANGED, HeatmapNode, MasteryChanged
from app.services.classes import ClassService
from app.services.mastery import MasteryService, NodeColumn
from app.services.skill_tree import SkillTreeService

if TYPE_CHECKING:
    from app.realtime.bus import EventBus

log = logging.getLogger(__name__)

# Đổi trạng thái nhưng không đổi số đã thử / số Đạt (Cell.effective_state xét IN_PROGRESS theo prev_state)
SKIP_REASONS = frozenset(
    {MasteryChangeReason.SESSION_STARTED, MasteryChangeReason.SESSION_ABANDONED, MasteryChangeReason.UNLOCKED}
)

Enqueue = Callable[[UUID, UUID], None]


def node_payload(node_id: UUID, node_key: str | None, st: NodeStat, rule: ColorRule) -> HeatmapNode:
    return HeatmapNode(
        node_id=node_id,
        node_key=node_key,
        color=st.color,
        pass_rate=st.pass_rate,
        attempted_rate=st.attempted_rate,
        sample=st.sample,
        label=st.label,
        enrolled_count=st.enrolled,
        attempted_count=st.attempted,
        passed_count=st.passed,
        min_sample=rule.min_sample,
    )


class HeatmapService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _lock(self, class_id: UUID) -> None:
        """Giữ khóa tới commit/rollback, trước khi đọc ma trận (kể cả chưa có dòng stats).

        Khóa theo lớp để đối soát cả lớp và tính từng nút dùng cùng thứ tự khóa.
        """
        self.db.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(f"heatmap:{class_id}", 0))))

    def rule(self, class_id: UUID) -> ColorRule:
        """Ngưỡng màu của lớp (BR-06; GV đổi qua PUT /classes/{id}/settings – C2-17)."""
        return ClassService(self.db).color_rule(class_id)

    def classify(self, stat: NodeStat, settings: ColorRule) -> NodeStat:
        """Phân màu lại một chỉ số theo ngưỡng khác (vd. GV xem trước cấu hình mới – C2-17)."""
        color, sample = classify(stat.attempted, stat.passed, settings)
        return replace(
            stat, color=color, sample=sample, label=label(color, sample, stat.attempted, stat.passed, settings)
        )

    def _save(self, class_id: UUID, col: NodeColumn, rule: ColorRule) -> HeatmapNode:
        st = aggregate(col.cells, col.enrolled, rule)
        values = {
            "enrolled_count": st.enrolled,
            "attempted_count": st.attempted,
            "passed_count": st.passed,
            "pass_rate": st.pass_rate,
            "avg_attempts": st.avg_attempts,
            "color": st.color.value,
            "updated_at": utcnow(),
        }
        stmt = insert(ClassNodeStat).values(class_id=class_id, node_id=col.node_id, **values)
        self.db.execute(stmt.on_conflict_do_update(index_elements=["class_id", "node_id"], set_=values))
        return node_payload(col.node_id, col.node_key, st, rule)

    def recompute(self, class_id: UUID, node_id: UUID) -> HeatmapNode | None:
        """Tính lại một nút và ghi class_node_stats (chưa commit). None khi nút không thuộc bản đang phát hành."""
        self._lock(class_id)
        rule = self.rule(class_id)
        cols = MasteryService(self.db, bus=_NO_BUS).columns(class_id, [node_id])
        if not cols:
            log.info("bỏ tính lại heatmap: nút %s không thuộc bản đang phát hành của lớp %s", node_id, class_id)
            return None
        return self._save(class_id, cols[0], rule)

    def recompute_class(self, class_id: UUID) -> list[HeatmapNode]:
        """Tính lại mọi nút của bản đang phát hành (chưa commit)."""
        self._lock(class_id)
        rule = self.rule(class_id)
        return [self._save(class_id, c, rule) for c in MasteryService(self.db, bus=_NO_BUS).columns(class_id)]

    def published_class_ids(self) -> list[UUID]:
        return SkillTreeService(self.db).published_class_ids()

    def snapshot(self, class_id):
        raise NotImplementedError("C2-13")

    def node_detail(self, class_id, node_id):
        raise NotImplementedError("C2-13")


class _NoBus:
    """HeatmapService chỉ đọc ma trận – không bao giờ phát sự kiện."""

    def publish(self, topic, event):  # pragma: no cover - không được gọi
        raise RuntimeError("HeatmapService không phát mastery.changed")


_NO_BUS = _NoBus()


def _enqueue_celery(class_id: UUID, node_id: UUID) -> None:
    from app.workers.aggregation import recompute_node

    recompute_node.delay(str(class_id), str(node_id))


def register_handlers(bus: "EventBus", enqueue: Enqueue | None = None) -> None:
    """Nghe `mastery.changed` → đẩy việc tính lại nút vào hàng đợi `aggregation`.
    Gọi một lần ở tiến trình nghe sự kiện (`python -m app.workers.mastery_listener`)."""
    push = enqueue or _enqueue_celery

    def on_mastery_changed(event: MasteryChanged) -> None:
        if event.reason in SKIP_REASONS:
            return
        try:
            push(event.class_id, event.node_id)
        except (KombuOperationalError, RedisError, OSError):
            # Broker rớt: không ném (bus chỉ ghi tên handler) – ghi đủ ngữ cảnh; đối soát định kỳ
            # (aggregation.reconcile_all, 10 phút) tính lại ô này. Lỗi khác (bug) vẫn ném để bus ghi log.
            log.exception(
                "không đẩy được tính lại heatmap: lớp %s, nút %s (%s) – chờ đối soát định kỳ",
                event.class_id,
                event.node_key or event.node_id,
                event.reason,
            )

    bus.subscribe(TOPIC_MASTERY_CHANGED, on_mastery_changed)
