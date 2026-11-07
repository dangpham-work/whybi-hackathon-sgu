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

C2-13 – realtime + ảnh chụp (FR-HM-02, 03, 06):
- `require_owner(class_id, user)`: chỉ GV phụ trách lớp (404 CLASS_NOT_FOUND / 403 NOT_CLASS_OWNER) – API và WebSocket.
- `snapshot(class_id)` → `HeatmapSnapshot` (cây, màu, lưới SV × nút có tên, cảnh báo), `node_detail(class_id, node_id)`.
  Cả hai tính TỪ MA TRẬN ĐANG ĐỌC (cùng thuật toán với hàng đợi) và KHÔNG ghi gì – GET không đổi CSDL.
- `push_updates(class_id, nodes, alerts)`: sau commit của hàng đợi `aggregation` → `heatmap.node` + `heatmap.alert`
  trên kênh class:{id}:heatmap. `push_cell` (task `aggregation.push_cell`) → `heatmap.cell` cho mọi mastery.changed,
  kể cả bắt đầu / bỏ dở phiên (lưới hiện "đang giảng"). Frontend bỏ cảnh báo của nút khi `heatmap.node` của nút đó
  không còn ĐỎ.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
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
from app.core.errors import AppError
from app.db.base import utcnow
from app.models.enums import MasteryChangeReason, MasteryState, Role
from app.models.peer import ClassNodeStat
from app.models.schemas import heatmap as out
from app.models.schemas.mastery import (
    TOPIC_MASTERY_CHANGED,
    HeatmapAlert,
    HeatmapCell,
    HeatmapNode,
    MasteryChanged,
)
from app.models.schemas.tree import Node
from app.services.classes import ClassService
from app.services.mastery import ClassMatrix, MasteryService, NodeColumn
from app.services.skill_tree import SkillTreeService

if TYPE_CHECKING:
    from app.api.deps import CurrentUser
    from app.realtime.bus import EventBus

log = logging.getLogger(__name__)

# Đổi trạng thái nhưng không đổi số đã thử / số Đạt (Cell.effective_state xét IN_PROGRESS theo prev_state)
SKIP_REASONS = frozenset(
    {MasteryChangeReason.SESSION_STARTED, MasteryChangeReason.SESSION_ABANDONED, MasteryChangeReason.UNLOCKED}
)

Enqueue = Callable[[UUID, UUID], None]
PushCell = Callable[[MasteryChanged], None]


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

    def update_settings(self, class_id: UUID, user: "CurrentUser", body: out.ClassSettings) -> out.ClassSettings:
        """PUT /classes/{id}/settings (FR-HM-08): lưu cấu hình rồi tính lại màu cả lớp và đẩy lên kênh heatmap."""
        self.require_owner(class_id, user)
        saved = ClassService(self.db).save_settings(class_id, body)
        nodes = self.recompute_class(class_id)
        alerts = self.trace_root_causes(class_id) if nodes else []
        self.db.commit()
        push_updates(class_id, nodes, alerts)  # sau commit, như hàng đợi aggregation
        return saved

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

    def _trace(self, m: ClassMatrix, rule: ColorRule) -> tuple[dict[str, NodeStat], dict[str, RootCause]]:
        """Chỉ số mọi nút + kết quả truy vết từ MỘT lần đọc ma trận (không ghi CSDL)."""
        everyone = set(m.students)
        stats, failed, not_mastered = {}, {}, {}
        for key, by_student in m.cells.items():
            cells = [by_student[s] for s in m.students if s in by_student]
            stats[key] = aggregate(cells, len(m.students), rule)
            failed[key] = {s for s, c in by_student.items() if c.attempted and not c.passed}
            not_mastered[key] = everyone - {s for s, c in by_student.items() if c.passed}
        colors = {k: st.color for k, st in stats.items()}
        found = trace_class(build_graph(m.tree), colors, failed, not_mastered, min_sample=rule.min_sample)
        return stats, found

    def trace_root_causes(self, class_id: UUID) -> list[HeatmapAlert]:
        """Mục 6.5.3: truy vết mọi nút đỏ, ghi root_cause_* vào class_node_stats (chưa commit), trả cảnh báo.

        Màu tính lại từ chính ma trận vừa đọc (cùng ngưỡng lớp) để F và màu nhất quán trong một lần đọc.
        Chỉ cập nhật dòng class_node_stats đã có (do `recompute` / `recompute_class` tạo)."""
        self._lock(class_id)  # khóa advisory theo giao dịch – gọi lại trong cùng giao dịch không tự chặn
        rule = self.rule(class_id)
        m = MasteryService(self.db, bus=_NO_BUS).class_matrix(class_id)
        _, found = self._trace(m, rule)
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

    # ------------------------------------------------------------------ C2-13: quyền, ảnh chụp, chi tiết nút

    def require_owner(self, class_id: UUID, user: "CurrentUser") -> None:
        """Bảng 5.13: bản đồ nhiệt chỉ cho GV phụ trách lớp."""
        lecturer_id = ClassService(self.db).lecturer_id(class_id)
        if user.role != Role.LECTURER or lecturer_id != user.id:
            raise AppError(403, "NOT_CLASS_OWNER", "Chỉ GV phụ trách lớp được xem bản đồ nhiệt")

    def _students(self, ids: list[UUID]) -> dict[UUID, tuple[str, str]]:
        """id → (họ tên, MSSV) – qua service người dùng, không truy vấn thẳng bảng users / students."""
        from app.services.auth import student_identities

        return student_identities(self.db, ids)

    def _view(self, class_id: UUID) -> "_View":
        rule = self.rule(class_id)
        m = MasteryService(self.db, bus=_NO_BUS).class_matrix(class_id)
        stats, found = self._trace(m, rule)
        nodes = {n.key: n for n in m.tree.nodes}
        alerts = {y: _alert(nodes[y], nodes[rc.node_key], rc) for y, rc in found.items()}
        roots = {rc.node_key for rc in found.values()}
        node_stats: dict[str, out.NodeStat] = {}
        for n in m.tree.nodes:
            st, rc = stats[n.key], found.get(n.key)
            node_stats[n.key] = out.NodeStat(
                node_id=n.id,
                node_key=n.key,
                code=n.code or "",
                title=n.title,
                color=st.color,
                pass_rate=st.pass_rate,
                attempted_count=st.attempted,
                passed_count=st.passed,
                attempted_rate=st.attempted_rate,
                enrolled_count=st.enrolled,
                sample=st.sample,
                label=st.label,
                is_root_cause=n.key in roots,
                root_cause_node_id=None if rc is None else nodes[rc.node_key].id,
                root_cause_node_key=None if rc is None else rc.node_key,
            )
        info = self._students(m.students)
        total = len(m.tree.nodes)
        rows: dict[UUID, out.GridRow] = {}
        for sid in m.students:
            by_key = {k: m.cells[k][sid] for k in nodes if sid in m.cells[k]}
            mastered = sum(1 for c in by_key.values() if c.passed)
            name, code = info.get(sid, ("", ""))
            rows[sid] = out.GridRow(
                student_id=sid,
                student_name=name,
                student_code=code,
                states={str(nodes[k].id): MasteryState(c.state) for k, c in by_key.items()},
                states_by_key={k: MasteryState(c.state) for k, c in by_key.items()},
                mastered_count=mastered,
                progress=mastered / total if total else 0.0,
            )
        return _View(m, nodes, node_stats, alerts, rows)

    @staticmethod
    def _hide_names(rows: dict[UUID, out.GridRow]) -> dict[UUID, out.GridRow]:
        """Chế độ trình chiếu (FR-HM-09): "SV 01", "SV 02"… theo thứ tự tên, bỏ MSSV – cùng một SV luôn cùng bí danh."""
        order = sorted(rows.values(), key=lambda r: (r.student_name, r.student_code))
        return {
            r.student_id: r.model_copy(update={"student_name": f"SV {i:02d}", "student_code": ""})
            for i, r in enumerate(order, 1)
        }

    def snapshot(self, class_id: UUID, q: str | None = None, anonymize: bool = False) -> out.HeatmapSnapshot:
        """GET /classes/{id}/heatmap – không ghi CSDL. 404 TREE_NOT_PUBLISHED khi lớp chưa phát hành cây.
        `q` lọc lưới theo tên / MSSV, `anonymize` ẩn tên khi chiếu (FR-HM-09); số liệu nút không đổi."""
        v = self._view(class_id)
        rows = self._hide_names(v.rows) if anonymize else v.rows
        grid = sorted(rows.values(), key=lambda r: (r.student_name, r.student_code))
        if q and q.strip():
            needle = q.strip().casefold()
            grid = [r for r in grid if needle in r.student_name.casefold() or needle in r.student_code.casefold()]
        active = sum(1 for col in v.matrix.cells.values() for c in col.values() if c.state == MasteryState.IN_PROGRESS)
        return out.HeatmapSnapshot(
            class_id=class_id,
            enrolled_count=len(v.matrix.students),
            active_sessions=active,
            nodes=list(v.node_stats.values()),
            grid=grid,
            alerts=list(v.alerts.values()),
            tree=v.matrix.tree,
        )

    def node_detail(self, class_id: UUID, node_id: UUID, anonymize: bool = False) -> out.NodeDetail:
        """GET /classes/{id}/nodes/{n}/detail – SV có tên theo trạng thái tại nút, quan niệm sai, nút gốc."""
        v = self._view(class_id)
        rows = self._hide_names(v.rows) if anonymize else v.rows
        key = next((k for k, n in v.nodes.items() if n.id == node_id), None)
        if key is None:
            raise AppError(
                404, "NODE_NOT_FOUND", "Nút không thuộc cây đang phát hành của lớp", {"nodeId": str(node_id)}
            )
        by_state: dict[str, list[out.GridRow]] = {}
        for sid, c in v.matrix.cells[key].items():
            by_state.setdefault(MasteryState(c.state).value, []).append(rows[sid])
        for group in by_state.values():
            group.sort(key=lambda r: (r.student_name, r.student_code))
        stat = v.node_stats[key]
        return out.NodeDetail(
            node_id=node_id,
            node_key=key,
            stat=stat,
            students_by_state=by_state,
            top_misconceptions=self._top_misconceptions(class_id, node_id),
            root_cause_node_id=stat.root_cause_node_id,
            alert=v.alerts.get(key),
        )

    def _top_misconceptions(self, class_id: UUID, node_id: UUID) -> list[dict]:
        """Đọc class_node_stats.top_misconceptions (bảng của heatmap). Chưa thẻ nào ghi cột này ⇒ []."""
        value = self.db.scalar(
            select(ClassNodeStat.top_misconceptions).where(
                ClassNodeStat.class_id == class_id, ClassNodeStat.node_id == node_id
            )
        )
        return list(value or [])

    def cell(self, event: MasteryChanged) -> HeatmapCell:
        """Payload heatmap.cell (Bảng 5.11) cho một mastery.changed – kèm tên và MSSV."""
        name, code = self._students([event.student_id]).get(event.student_id, ("", ""))
        return HeatmapCell(
            student_id=event.student_id,
            student_name=name,
            student_code=code or None,
            node_id=event.node_id,
            node_key=event.node_key,
            state=event.new_state,
        )

    def published_class_ids(self) -> list[UUID]:
        return SkillTreeService(self.db).published_class_ids()


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


@dataclass(frozen=True)
class _View:
    matrix: ClassMatrix
    nodes: dict[str, Node]
    node_stats: dict[str, out.NodeStat]
    alerts: dict[str, HeatmapAlert]
    rows: dict[UUID, out.GridRow]


def push_updates(class_id: UUID, nodes: list[HeatmapNode], alerts: list[HeatmapAlert]) -> None:
    """C2-13: gọi SAU commit – phát heatmap.node rồi heatmap.alert lên class:{id}:heatmap.
    Redis rớt: chỉ ghi log (số liệu đã lưu; GV tải lại ảnh chụp khi WebSocket nối lại)."""
    from app.realtime import gateway

    channel = gateway.channel_heatmap(class_id)
    try:
        for node in nodes:
            gateway.broadcast(channel, gateway.EVENT_HEATMAP_NODE, node)
        for alert in alerts:
            gateway.broadcast(channel, gateway.EVENT_HEATMAP_ALERT, alert)
    except (RedisError, OSError):
        log.exception("không phát được heatmap.node / heatmap.alert cho lớp %s", class_id)


def push_cell(class_id: UUID, cell: HeatmapCell) -> None:
    """C2-13: phát heatmap.cell (Redis rớt: chỉ ghi log)."""
    from app.realtime import gateway

    try:
        gateway.broadcast(gateway.channel_heatmap(class_id), gateway.EVENT_HEATMAP_CELL, cell)
    except (RedisError, OSError):
        log.exception("không phát được heatmap.cell: lớp %s, SV %s, nút %s", class_id, cell.student_id, cell.node_id)


def _push_cell_celery(event: MasteryChanged) -> None:
    from app.workers.aggregation import push_cell as task

    task.delay(event.model_dump_json(by_alias=True))


def register_handlers(bus: "EventBus", enqueue: Enqueue | None = None, cell: PushCell | None = None) -> None:
    """Nghe `mastery.changed` → đẩy việc tính lại nút vào hàng đợi `aggregation`; C2-13: đẩy cả việc phát heatmap.cell.
    Gọi một lần ở tiến trình nghe sự kiện (`python -m app.workers.mastery_listener`).
    Test truyền `enqueue` mà không truyền `cell` ⇒ không phát heatmap.cell (không chạm Celery)."""
    push = enqueue or _enqueue_celery
    on_cell = cell if cell is not None else (_push_cell_celery if enqueue is None else None)

    def on_mastery_changed(event: MasteryChanged) -> None:
        if on_cell is not None:
            try:
                on_cell(event)
            except (KombuOperationalError, RedisError, OSError):
                log.exception("không đẩy được heatmap.cell: lớp %s, SV %s", event.class_id, event.student_id)
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
