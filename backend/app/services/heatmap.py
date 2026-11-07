"""HeatmapService – HeatmapAggregator: tính chỉ số nút, phân màu BR-06, truy vết gốc, đẩy WebSocket (mục 6.5).
Chủ: Long (C2-11…C2-13).

C2-11 (đã làm):
- `mastery.changed` → `register_handlers` đẩy (class_id, node_id) vào hàng đợi `aggregation`
  (`app.workers.aggregation.recompute_node`). Bỏ qua lý do không đổi số liệu (bắt đầu / bỏ dở phiên, mở khóa).
- `recompute(class_id, node_id)` đọc cột ma trận qua `MasteryService.columns` (không truy vấn thẳng mastery_records),
  tính chỉ số + màu bằng `app.algorithms.heatmap`, ghi đè dòng `class_node_stats` (upsert, idempotent),
  trả `HeatmapNode` (kèm `nodeKey`, `label`) cho C2-13 đẩy lên kênh class:{id}:heatmap.
- `recompute_class(class_id)` tính lại mọi nút – dùng khi đối soát định kỳ (bù sự kiện Pub/Sub bị mất).
Không ghi `top_misconceptions` (C2-13 chi tiết nút).

C2-12 (đã làm) – truy vết điểm nghẽn gốc (mục 6.5.3, Hình 6.10):
- `trace_root_causes(class_id)` đọc cả ma trận qua `MasteryService.class_matrix` (không truy vấn thẳng
  mastery_records), dựng DAG từ bản đang phát hành, truy vết mọi nút ĐỎ bằng `app.algorithms.rootcause`.
- Ghi `class_node_stats.root_cause_node_id / root_cause_score` cho MỌI nút của lớp (nút không còn đỏ / không đủ
  mẫu trượt ⇒ xóa về NULL), trả `HeatmapAlert` ("Nên giảng lại X") cho C2-13 đẩy `heatmap.alert`.
- Hàng đợi `aggregation` gọi sau mỗi lần tính lại (một nút đổi có thể đổi r(X|Y) của mọi nút con cháu).
- "Chưa Đạt X" dùng cùng định nghĩa Đạt với bản đồ nhiệt (MASTERED / NEEDS_REVERIFY – BR-02); SV chưa có ô ⇒ chưa Đạt.
"""

import logging
from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING
from uuid import UUID

from kombu.exceptions import OperationalError as KombuOperationalError
from redis.exceptions import RedisError
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.algorithms.dag import build_graph
from app.algorithms.heatmap import ColorRule, NodeStat, aggregate, classify, label
from app.algorithms.rootcause import RootCause, alert_message, trace_class
from app.db.base import utcnow
from app.models.enums import MasteryChangeReason
from app.models.peer import ClassNodeStat
from app.models.schemas.mastery import TOPIC_MASTERY_CHANGED, HeatmapAlert, HeatmapNode, MasteryChanged
from app.models.schemas.tree import Node
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

    def trace_root_causes(self, class_id: UUID) -> list[HeatmapAlert]:
        """Mục 6.5.3: truy vết mọi nút đỏ, ghi root_cause_* vào class_node_stats (chưa commit), trả cảnh báo.

        Màu tính lại từ chính ma trận vừa đọc (cùng ngưỡng lớp) để F và màu nhất quán trong một lần đọc.
        Chỉ cập nhật dòng class_node_stats đã có (do `recompute` / `recompute_class` tạo)."""
        self._lock(class_id)  # khóa advisory theo giao dịch – gọi lại trong cùng giao dịch không tự chặn
        rule = self.rule(class_id)
        m = MasteryService(self.db, bus=_NO_BUS).class_matrix(class_id)
        everyone = set(m.students)
        colors, failed, not_mastered = {}, {}, {}
        for key, by_student in m.cells.items():
            cells = [by_student[s] for s in m.students if s in by_student]
            colors[key] = aggregate(cells, len(m.students), rule).color
            failed[key] = {s for s, c in by_student.items() if c.attempted and not c.passed}
            not_mastered[key] = everyone - {s for s, c in by_student.items() if c.passed}
        found = trace_class(build_graph(m.tree), colors, failed, not_mastered, min_sample=rule.min_sample)
        nodes = {n.key: n for n in m.tree.nodes}
        for key, n in nodes.items():
            rc = found.get(key)
            self.db.execute(
                update(ClassNodeStat)
                .where(ClassNodeStat.class_id == class_id, ClassNodeStat.node_id == n.id)
                .values(
                    root_cause_node_id=None if rc is None else nodes[rc.node_key].id,
                    root_cause_score=None if rc is None else rc.score,
                )
            )
        return [_alert(nodes[y], nodes[rc.node_key], rc) for y, rc in found.items()]

    def published_class_ids(self) -> list[UUID]:
        return SkillTreeService(self.db).published_class_ids()

    def snapshot(self, class_id):
        raise NotImplementedError("C2-13")

    def node_detail(self, class_id, node_id):
        raise NotImplementedError("C2-13")


def _alert(y: Node, x: Node, rc: RootCause) -> HeatmapAlert:
    """Y: nút đỏ; X: nút nên giảng lại (= Y khi Y tự là điểm nghẽn)."""
    return HeatmapAlert(
        node_id=y.id,
        node_key=y.key,
        root_cause_node_id=x.id,
        root_cause_node_key=x.key,
        root_cause_title=x.title,
        message=alert_message(x.code, x.title),
        is_self=rc.is_self,
        score=rc.score,
        conditional_fail_rate=rc.conditional_fail_rate,
        failed_count=rc.failed_count,
        distance=rc.distance,
    )


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
