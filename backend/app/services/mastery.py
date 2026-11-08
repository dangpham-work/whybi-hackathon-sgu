"""MasteryService – Ma trận thành thạo + MasteryStateMachine (Bảng 4.8, BR-02, BR-11, BR-14). Chủ: Long (C2-10).

Là nơi DUY NHẤT ghi `mastery_records`. Mỗi lần đổi ô ⇒ phát `mastery.changed` (MasteryChanged, có `reason`)
SAU khi commit (bên nghe đọc lại CSDL thấy đúng dữ liệu).

Bên gọi:
- SkillTreeService.publish (C2-09) → `init_or_migrate(class_id, version_id)` – khởi tạo / di chuyển (BR-14);
  hàm này commit luôn giao dịch phát hành của bên gọi.
- SessionOrchestrator (Đăng, C1-07):
    `start_session(student_id, node_id, session_id)` sau khi tạo TeachingSession, trước khi chạy phiên – lỗi xem
    schemas/mastery.py; `abandon(student_id, node_id, session_id)` khi bỏ dở / hết hạn;
    kết quả chấm đi qua sự kiện `session.completed` → `apply_result(SessionResult)` (`register_handlers`).
- Tham gia lớp sau khi đã phát hành (C2-08) → `ensure_student(class_id, student_id)` (my_map cũng tự tạo ô còn thiếu).
- GET /classes/{id}/my-map → `my_map(class_id, student_id)`.
- HeatmapService (C2-11) → `columns(class_id, node_ids)` (chỉ đọc); (C2-12) → `class_matrix(class_id)` (chỉ đọc).

Quy ước:
- Mỗi (SV, key nút) có đúng một dòng; phát hành phiên bản mới thì CHUYỂN dòng sang nút cùng key ở phiên bản mới
  (giữ attempts, best_score). Nút bị bỏ khỏi cây giữ dòng cũ (lịch sử), mọi phép đọc chỉ lấy nút của bản đang phát hành.
- `node_id` từ bên gọi có thể thuộc phiên bản cũ (phiên bắt đầu trước khi GV phát hành) – luôn ánh xạ theo key.
- Tiên quyết NEEDS_REVERIFY vẫn tính là đã Đạt (BR-02 không khóa lại nút con khi chỉ đổi rubric).
"""

import json
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.algorithms.dag import build_graph, frontier
from app.algorithms.heatmap import Cell
from app.core.errors import AppError
from app.models import tree as orm
from app.models.enums import MasteryChangeReason, MasteryState, Verdict
from app.models.schemas.mastery import (
    RETRY_COOLDOWN_MINUTES,
    TOPIC_MASTERY_CHANGED,
    TOPIC_SESSION_COMPLETED,
    MasteryChanged,
    MyMap,
    NodeProgress,
    StartCheck,
)
from app.models.schemas.session import SessionResult
from app.models.schemas.tree import Rubric, TreeVersion
from app.models.session import Evaluation, MasteryRecord
from app.models.users import ClassSection, Enrollment
from app.realtime.bus import get_bus
from app.services.skill_tree import SkillTreeService

if TYPE_CHECKING:
    from app.realtime.bus import EventBus

log = logging.getLogger(__name__)

S = MasteryState
R = MasteryChangeReason
DONE = frozenset({S.MASTERED, S.NEEDS_REVERIFY})  # tính là đã Đạt khi xét tiên quyết
STARTABLE = frozenset({S.AVAILABLE, S.NOT_PASSED, S.NEEDS_REVERIFY})
COOLDOWN = timedelta(minutes=RETRY_COOLDOWN_MINUTES)


@dataclass(frozen=True)
class NodeColumn:
    """Một cột M[·, nút] của SV đang ghi danh (C2-11)."""

    node_id: UUID
    node_key: str
    enrolled: int
    cells: list[Cell]


@dataclass(frozen=True)
class ClassMatrix:
    """Ma trận M[SV, nút] của bản đang phát hành – đầu vào truy vết điểm nghẽn gốc (C2-12). Chỉ đọc.

    `cells[key][student_id]`; SV đang ghi danh chưa có ô ở nút nào thì không có mục (coi như chưa thử, chưa Đạt)."""

    tree: TreeVersion
    students: list[UUID]
    cells: dict[str, dict[UUID, Cell]]


@dataclass
class _Tree:
    """Bản đang phát hành của một lớp, tra theo key."""

    class_id: UUID
    schema: TreeVersion
    id_of: dict[str, UUID] = field(default_factory=dict)
    key_of: dict[UUID, str] = field(default_factory=dict)
    prereqs: dict[str, list[str]] = field(default_factory=dict)
    children: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def of(cls, class_id: UUID, schema: TreeVersion) -> "_Tree":
        t = cls(class_id=class_id, schema=schema)
        for n in schema.nodes:
            t.id_of[n.key] = n.id
            t.key_of[n.id] = n.key
            t.prereqs[n.key] = []
            t.children[n.key] = []
        for e in schema.edges:
            t.prereqs[e.to_key].append(e.from_key)
            t.children[e.from_key].append(e.to_key)
        return t

    def missing(self, key: str, done: set[str]) -> list[str]:
        return [p for p in self.prereqs[key] if p not in done]


def _rubric_sig(r: Rubric | None) -> dict | None:
    """Phần rubric dùng để so "rubric đổi" (BR-14) – bỏ cờ duyệt (bản nháp mới luôn phải duyệt lại)."""
    return None if r is None else r.model_dump(mode="json", exclude={"approved"})


@dataclass
class MatchingSnapshot:
    """Ảnh chụp CHỈ ĐỌC ma trận cả lớp theo bản đang phát hành (ghép cặp C2-14 dùng)."""

    version_id: UUID
    id_of: dict[str, UUID]  # key nút → id ở bản đang phát hành
    mastered: dict[UUID, set[str]]  # SV → key đã Đạt (tính cả NEEDS_REVERIFY như khi xét tiên quyết)
    frontier: dict[UUID, set[str]]  # SV → Biên: chưa Đạt, mọi tiên quyết đã Đạt
    pass_rate: dict[str, float]  # key → tỉ lệ SV ghi danh đã Đạt


@dataclass
class NodeOutcomes:
    """Kết quả của SV đang ghi danh ở một nút, theo thời gian (ghép cặp theo sự kiện C2-15). Chỉ đọc."""

    node_id: UUID | None  # id nút ở bản đang phát hành; None khi key không còn trong cây
    passed: list[tuple[UUID, datetime]]  # đã Đạt, Đạt sớm → muộn
    failed: list[tuple[UUID, datetime]]  # chưa Đạt nhưng đã trượt (kèm lần trượt gần nhất), đến trước → sau


class MasteryService:
    def pending_results(self, session_ids: Iterable[UUID]) -> set[UUID]:
        """Các phiên vẫn có ô IN_PROGRESS, dùng đối soát sự kiện hoàn tất bị mất."""
        ids = list(session_ids)
        if not ids:
            return set()
        q = select(MasteryRecord.last_session_id).where(
            MasteryRecord.state == MasteryState.IN_PROGRESS, MasteryRecord.last_session_id.in_(ids)
        )
        return {sid for sid in self.db.scalars(q) if sid is not None}

    def __init__(self, db: Session, bus: "EventBus | None" = None) -> None:
        self.db = db
        self.bus = bus if bus is not None else get_bus()

    # ------------------------------------------------------------------ nạp dữ liệu

    def _tree(self, class_id: UUID) -> _Tree:
        if self.db.get(ClassSection, class_id) is None:
            raise AppError(404, "CLASS_NOT_FOUND", "Không tìm thấy lớp", {"classId": str(class_id)})
        version_id = self.db.scalar(
            select(orm.SkillTree.published_version_id).where(orm.SkillTree.class_id == class_id)
        )
        if version_id is None:
            raise AppError(404, "TREE_NOT_PUBLISHED", "Lớp chưa phát hành cây kỹ năng")
        return _Tree.of(class_id, SkillTreeService(self.db).version_schema(version_id))

    def _node_class_key(self, node_id: UUID) -> tuple[UUID, str]:
        row = self.db.execute(
            select(orm.SkillTree.class_id, orm.ConceptNode.key)
            .join(orm.TreeVersion, orm.TreeVersion.id == orm.ConceptNode.version_id)
            .join(orm.SkillTree, orm.SkillTree.id == orm.TreeVersion.tree_id)
            .where(orm.ConceptNode.id == node_id)
        ).first()
        if row is None:
            raise AppError(404, "NODE_NOT_FOUND", "Không tìm thấy nút", {"nodeId": str(node_id)})
        return row[0], row[1]

    def _enrolled(self, class_id: UUID, student_ids: Iterable[UUID] | None = None) -> list[UUID]:
        """Khóa dòng ghi danh (theo thứ tự id) để hai lời gọi song song không cùng tạo ô cho một SV."""
        q = select(Enrollment.student_id).where(Enrollment.class_id == class_id)
        if student_ids is not None:
            q = q.where(Enrollment.student_id.in_(list(student_ids)))
        return list(self.db.scalars(q.order_by(Enrollment.student_id).with_for_update()))

    def _require_enrolled(self, class_id: UUID, student_id: UUID) -> None:
        if not self._enrolled(class_id, [student_id]):
            raise AppError(403, "NOT_ENROLLED", "Bạn chưa tham gia lớp này")

    def _rows(self, t: _Tree, student_id: UUID, *, lock: bool = False) -> dict[str, MasteryRecord]:
        q = select(MasteryRecord).where(
            MasteryRecord.student_id == student_id, MasteryRecord.node_id.in_(list(t.key_of))
        )
        if lock:
            q = q.with_for_update()
        return {t.key_of[r.node_id]: r for r in self.db.scalars(q.execution_options(populate_existing=True))}

    # ------------------------------------------------------------------ khởi tạo / di chuyển (Bảng 4.8 dòng 1–2, BR-14)

    def _sync(self, t: _Tree, student_ids: list[UUID]) -> list[MasteryChanged]:
        """Đảm bảo mỗi SV có đủ ô cho mọi nút của bản đang phát hành. Không commit."""
        version_id = t.schema.id
        new_rubric = {n.key: _rubric_sig(n.rubric) for n in t.schema.nodes}
        old_rubric_cache: dict[UUID, dict[str, dict | None]] = {}
        changes: list[MasteryChanged] = []
        for sid in student_ids:
            rows = self._rows(t, sid, lock=True)
            missing = [k for k in t.id_of if k not in rows]
            if not missing:
                continue
            # ô cũ cùng key ở phiên bản trước (mới nhất nếu có nhiều)
            old: dict[str, tuple[MasteryRecord, UUID]] = {}
            q = (
                select(MasteryRecord, orm.ConceptNode.key, orm.ConceptNode.version_id)
                .join(orm.ConceptNode, orm.ConceptNode.id == MasteryRecord.node_id)
                .where(
                    MasteryRecord.student_id == sid,
                    MasteryRecord.class_id == t.class_id,
                    orm.ConceptNode.key.in_(missing),
                    orm.ConceptNode.version_id != version_id,
                )
                .order_by(MasteryRecord.updated_at)
                .with_for_update(of=MasteryRecord)
            )
            for rec, key, vid in self.db.execute(q):
                old[key] = (rec, vid)

            before: dict[str, S | None] = {}
            for key in missing:
                if key in old:
                    rec, vid = old[key]
                    if vid not in old_rubric_cache:
                        sch = SkillTreeService(self.db).version_schema(vid)
                        old_rubric_cache[vid] = {n.key: _rubric_sig(n.rubric) for n in sch.nodes}
                    before[key] = S(rec.state)
                    rec.node_id = t.id_of[key]
                    if rec.state == S.MASTERED and old_rubric_cache[vid].get(key) != new_rubric[key]:
                        rec.state = S.NEEDS_REVERIFY
                else:
                    rec = MasteryRecord(student_id=sid, node_id=t.id_of[key], class_id=t.class_id, state=S.LOCKED)
                    rec.attempts = 0
                    self.db.add(rec)
                    before[key] = None
                rows[key] = rec

            done = {k for k, r in rows.items() if r.state in DONE}
            for key in missing:
                rec = rows[key]
                if rec.state in DONE or rec.state == S.IN_PROGRESS:
                    continue  # phiên đang chạy giữ nguyên – kết quả sẽ ghi vào nút mới theo key
                if t.missing(key, done):
                    rec.state = S.LOCKED
                elif rec.state == S.LOCKED:
                    rec.state = S.AVAILABLE
            self.db.flush()
            for key in missing:
                rec, old_state = rows[key], before[key]
                if old_state is None or old_state != rec.state:
                    changes.append(
                        self._event(t, rec, key, old_state, R.PUBLISH_INIT if old_state is None else R.PUBLISH_MIGRATE)
                    )
        return changes

    def init_or_migrate(self, class_id: UUID, version_id: UUID) -> list[MasteryChanged]:
        """Phát hành `version_id`: đồng bộ ma trận + thống kê cùng giao dịch, commit rồi phát sự kiện."""
        from app.services.heatmap import HeatmapService

        students = self._enrolled(class_id)
        t = self._tree(class_id)
        if t.schema.id != version_id:
            raise AppError(409, "VERSION_NOT_PUBLISHED", "Phiên bản chưa phải bản đang phát hành của lớp")
        changes = self._sync(t, students)
        # node_id đổi dù trạng thái giữ nguyên; lớp rỗng cũng cần đủ thống kê nút mới.
        heat = HeatmapService(self.db)
        heat.recompute_class(class_id)
        heat.trace_root_causes(class_id)  # C2-12: nút mới có id mới – ghi lại gốc ngay, không chờ đối soát
        return self._commit(changes)

    def ensure_student(self, class_id: UUID, student_id: UUID) -> list[MasteryChanged]:
        """SV vào lớp sau khi đã phát hành: tạo ô còn thiếu. Lớp chưa phát hành ⇒ không làm gì."""
        try:
            t = self._tree(class_id)
        except AppError as exc:
            if exc.code == "TREE_NOT_PUBLISHED":
                return []
            raise
        self._require_enrolled(class_id, student_id)
        t = self._tree(class_id)  # có thể vừa phát hành bản mới trong lúc chờ khóa ghi danh
        return self._commit(self._sync(t, [student_id]))

    # ------------------------------------------------------------------ đọc

    def _progress(self, t: _Tree, key: str, rec: MasteryRecord, done: set[str], now: datetime) -> NodeProgress:
        state = S(rec.state)
        retry_at = None
        if state == S.NOT_PASSED and rec.last_failed_at is not None and rec.last_failed_at + COOLDOWN > now:
            retry_at = rec.last_failed_at + COOLDOWN
        return NodeProgress(
            node_id=t.id_of[key],
            node_key=key,
            state=state,
            best_score=float(rec.best_score) if rec.best_score is not None else None,
            attempts=rec.attempts or 0,
            missing_prerequisites=t.missing(key, done) if state == S.LOCKED else [],
            retry_at=retry_at,
            can_start=state in STARTABLE and retry_at is None,
            last_session_id=rec.last_session_id,
            updated_at=rec.updated_at,
        )

    def _check(self, t: _Tree, key: str, rec: MasteryRecord, done: set[str]) -> tuple[StartCheck, dict]:
        p = self._progress(t, key, rec, done, datetime.now(UTC))
        code, details = None, {}
        if p.state == S.LOCKED:
            code, details = "NODE_LOCKED", {"missingPrerequisites": p.missing_prerequisites}
        elif p.state == S.IN_PROGRESS:
            code, details = (
                "SESSION_IN_PROGRESS",
                {"sessionId": str(rec.last_session_id) if rec.last_session_id else None},
            )
        elif p.state == S.MASTERED:
            code = "NODE_ALREADY_MASTERED"
        elif p.retry_at is not None:
            code, details = "RETRY_COOLDOWN", {"retryAt": p.retry_at.isoformat()}
        check = StartCheck(
            allowed=code is None,
            code=code,
            state=p.state,
            missing_prerequisites=p.missing_prerequisites,
            retry_at=p.retry_at,
        )
        return check, details

    def _cell(
        self, student_id: UUID, node_id: UUID
    ) -> tuple[_Tree, str, dict[str, MasteryRecord], list[MasteryChanged]]:
        """Bản đang phát hành + ô (đã khóa dòng) của SV ở nút cùng key với `node_id`."""
        class_id, key = self._node_class_key(node_id)
        t = self._tree(class_id)
        self._require_enrolled(class_id, student_id)
        t = self._tree(class_id)  # đồng bộ theo bản hiện tại sau khi đã lấy khóa, không chuyển ngược về bản cũ
        if key not in t.id_of:
            raise AppError(404, "NODE_NOT_FOUND", "Nút không còn trong cây đang phát hành", {"nodeKey": key})
        changes = self._sync(t, [student_id])
        return t, key, self._rows(t, student_id, lock=True), changes

    def can_start(self, student_id: UUID, node_id: UUID) -> StartCheck:
        """Kiểm tra không commit giao dịch của bên gọi, cũng không lưu / phát sự kiện cho ô tạo tạm.
        start_session kiểm tra lại và ghi thay đổi thật trong giao dịch mở phiên."""
        savepoint = self.db.begin_nested()
        try:
            t, key, rows, _ = self._cell(student_id, node_id)
            done = {k for k, r in rows.items() if r.state in DONE}
            check, _ = self._check(t, key, rows[key], done)
            return check
        finally:
            savepoint.rollback()

    def matching_snapshot(self, class_id: UUID) -> MatchingSnapshot:
        """Đọc ma trận mọi SV ghi danh – không khóa, không tạo ô, không commit. Ô chưa có coi như chưa Đạt."""
        t = self._tree(class_id)
        students = list(self.db.scalars(select(Enrollment.student_id).where(Enrollment.class_id == class_id)))
        done: dict[UUID, set[str]] = {s: set() for s in students}
        if students:
            rows = self.db.execute(
                select(MasteryRecord.student_id, MasteryRecord.node_id, MasteryRecord.state).where(
                    MasteryRecord.student_id.in_(students), MasteryRecord.node_id.in_(list(t.key_of))
                )
            )
            for sid, nid, state in rows:
                if state in DONE:
                    done[sid].add(t.key_of[nid])
        g = build_graph(t.schema)
        n = len(students)
        return MatchingSnapshot(
            version_id=t.schema.id,
            id_of=dict(t.id_of),
            mastered=done,
            frontier={s: frontier(g, d) for s, d in done.items()},
            pass_rate={k: (sum(k in d for d in done.values()) / n if n else 0.0) for k in t.id_of},
        )

    def node_outcomes(self, class_id: UUID, node_key: str) -> NodeOutcomes:
        """Ai đã Đạt / đã trượt nút `node_key` ở bản đang phát hành – không khóa, không tạo ô, không commit.
        Đã Đạt = MASTERED hoặc NEEDS_REVERIFY (mốc là lần cập nhật ô); đã trượt = chưa Đạt và có `last_failed_at`."""
        node_id = self._tree(class_id).id_of.get(node_key)
        if node_id is None:
            return NodeOutcomes(None, [], [])
        rows = self.db.execute(
            select(
                MasteryRecord.student_id, MasteryRecord.state, MasteryRecord.updated_at, MasteryRecord.last_failed_at
            )
            .join(Enrollment, (Enrollment.student_id == MasteryRecord.student_id) & (Enrollment.class_id == class_id))
            .where(MasteryRecord.node_id == node_id)
            .order_by(MasteryRecord.updated_at, MasteryRecord.student_id)
        ).all()
        passed = [(s, updated) for s, state, updated, _ in rows if state in DONE]
        failed = [(s, at) for s, state, _, at in rows if state not in DONE and at is not None]
        return NodeOutcomes(node_id, passed, sorted(failed, key=lambda x: (x[1], str(x[0]))))

    def my_map(self, class_id: UUID, student_id: UUID) -> MyMap:
        t = self._tree(class_id)
        self._require_enrolled(class_id, student_id)
        t = self._tree(class_id)
        changes = self._sync(t, [student_id])
        rows = self._rows(t, student_id)
        done = {k for k, r in rows.items() if r.state in DONE}
        now = datetime.now(UTC)
        progress = [self._progress(t, n.key, rows[n.key], done, now) for n in t.schema.nodes]
        order = {n.key: i for i, n in enumerate(t.schema.nodes)}
        result = MyMap(
            class_id=class_id,
            student_id=student_id,
            tree=t.schema,
            progress=progress,
            frontier=sorted(frontier(build_graph(t.schema), done), key=order.__getitem__),
            mastered_count=sum(1 for p in progress if p.state == S.MASTERED),
            total_count=len(progress),
        )
        # Dựng response khi còn giữ khóa: phát hành sau commit có thể di chuyển các dòng sang node_id mới.
        self._commit(changes)
        return result

    def columns(self, class_id: UUID, node_ids: Iterable[UUID] | None = None) -> list["NodeColumn"]:
        """Cột ma trận theo nút của bản đang phát hành – đầu vào cho HeatmapService (C2-11). Chỉ đọc, không khóa.

        Chỉ tính SV đang ghi danh. `node_ids` lọc nút; id không thuộc bản đang phát hành bị bỏ qua
        (sự kiện cũ đến sau khi GV phát hành bản mới)."""
        # Không dựng cả TreeVersion như _tree(): mỗi sự kiện gọi một lần, phát hành 30 SV × 11 nút = 330 lần.
        wanted_ids = None if node_ids is None else list(node_ids)
        key_of = SkillTreeService(self.db).published_node_keys(class_id, wanted_ids)
        wanted = list(key_of)
        if not wanted:
            return []
        enrolled = select(Enrollment.student_id).where(Enrollment.class_id == class_id)
        enrolled_count = self.db.scalar(select(func.count()).select_from(enrolled.subquery())) or 0
        cells: dict[UUID, list[Cell]] = {n: [] for n in wanted}
        q = select(MasteryRecord.node_id, MasteryRecord.state, MasteryRecord.attempts, MasteryRecord.prev_state).where(
            MasteryRecord.class_id == class_id,
            MasteryRecord.node_id.in_(wanted),
            MasteryRecord.student_id.in_(enrolled),
        )
        for node_id, state, attempts, prev in self.db.execute(q):
            cells[node_id].append(Cell(S(state), attempts or 0, S(prev) if prev else None))
        return [NodeColumn(n, key_of[n], enrolled_count, cells[n]) for n in wanted]

    def class_matrix(self, class_id: UUID) -> ClassMatrix:
        """Cả ma trận của SV đang ghi danh theo bản đang phát hành – cho HeatmapService truy vết gốc (C2-12).
        Chỉ đọc, không khóa. 404 CLASS_NOT_FOUND / TREE_NOT_PUBLISHED như `_tree`."""
        t = self._tree(class_id)
        enrolled = select(Enrollment.student_id).where(Enrollment.class_id == class_id)
        students = list(self.db.scalars(enrolled.order_by(Enrollment.student_id)))
        cells: dict[str, dict[UUID, Cell]] = {k: {} for k in t.id_of}
        q = select(
            MasteryRecord.student_id,
            MasteryRecord.node_id,
            MasteryRecord.state,
            MasteryRecord.attempts,
            MasteryRecord.prev_state,
        ).where(
            MasteryRecord.class_id == class_id,
            MasteryRecord.node_id.in_(list(t.key_of)),
            MasteryRecord.student_id.in_(enrolled),
        )
        for student_id, node_id, state, attempts, prev in self.db.execute(q):
            cells[t.key_of[node_id]][student_id] = Cell(S(state), attempts or 0, S(prev) if prev else None)
        return ClassMatrix(tree=t.schema, students=students, cells=cells)

    # ------------------------------------------------------------------ phiên (Bảng 4.8)

    def start_session(self, student_id: UUID, node_id: UUID, session_id: UUID) -> NodeProgress:
        """AVAILABLE / NOT_PASSED (hết chờ) / NEEDS_REVERIFY → IN_PROGRESS rồi commit (kèm giao dịch của bên gọi).
        Không hợp lệ ⇒ AppError 409, KHÔNG commit – bên gọi rollback."""
        t, key, rows, changes = self._cell(student_id, node_id)
        rec = rows[key]
        done = {k for k, r in rows.items() if r.state in DONE}
        check, details = self._check(t, key, rec, done)
        if not check.allowed:
            # Không commit: bên gọi (Orchestrator) rollback được TeachingSession vừa tạo. Ô do _sync tạo cũng
            # rollback theo – lần gọi sau tạo lại, sự kiện khởi tạo phát lúc đó.
            raise AppError(409, check.code, _MESSAGES[check.code], details)
        old = S(rec.state)
        rec.prev_state = old
        rec.state = S.IN_PROGRESS
        rec.last_session_id = session_id
        self.db.flush()
        changes.append(self._event(t, rec, key, old, R.SESSION_STARTED, session_id=session_id))
        self._commit(changes)
        return self._progress(t, key, rec, done, datetime.now(UTC))

    def abandon(self, student_id: UUID, node_id: UUID, session_id: UUID) -> NodeProgress:
        """Bỏ dở / hết hạn: quay lại trạng thái trước phiên (chưa từng trượt ⇒ AVAILABLE, đã trượt ⇒ NOT_PASSED,
        phiên xác nhận lại ⇒ NEEDS_REVERIFY). Phiên khác / ô không IN_PROGRESS ⇒ giữ nguyên (gọi lặp an toàn)."""
        t, key, rows, changes = self._cell(student_id, node_id)
        rec = rows[key]
        if rec.state == S.IN_PROGRESS and rec.last_session_id == session_id:
            fallback = S.NOT_PASSED if rec.attempts else S.AVAILABLE
            rec.state = S(rec.prev_state) if rec.prev_state in STARTABLE else fallback
            rec.prev_state = None
            self.db.flush()
            changes.append(self._event(t, rec, key, S.IN_PROGRESS, R.SESSION_ABANDONED, session_id=session_id))
        self._commit(changes)
        done = {k for k, r in rows.items() if r.state in DONE}
        return self._progress(t, key, rec, done, datetime.now(UTC))

    def apply_result(self, result: SessionResult) -> MasteryChanged | None:
        """Chấm xong (session.completed): PASSED ⇒ MASTERED + mở khóa nút con (BR-02); FAILED ⇒ NOT_PASSED (BR-11).
        Trả None khi bỏ qua: ô không IN_PROGRESS ở đúng phiên này (gửi lặp, phiên đã bỏ dở, phiên lạ)."""
        t, key, rows, changes = self._cell(result.student_id, result.node_id)
        rec = rows[key]
        state = S(rec.state)
        if state != S.IN_PROGRESS or rec.last_session_id != result.session_id:
            # Chỉ nhận kết quả của đúng phiên đang IN_PROGRESS (start_session bắt buộc trước phiên).
            # Cùng phiên mà ô đã rời IN_PROGRESS = tin gửi lặp hoặc phiên đã bỏ dở / hết hạn ⇒ bỏ, mức INFO.
            # Phiên lạ (chưa start_session, hoặc phiên cũ về muộn khi đã có phiên mới) ⇒ bỏ, mức ERROR.
            same = rec.last_session_id == result.session_id
            log.log(
                logging.INFO if same else logging.ERROR,
                "bỏ kết quả phiên %s (%s, %.1f điểm): SV %s, lớp %s, nút %s đang %s, phiên hiện tại %s",
                result.session_id,
                result.verdict,
                result.total_score,
                result.student_id,
                t.class_id,
                key,
                state,
                rec.last_session_id,
            )
            self._commit(changes)
            return None

        passed = result.verdict == Verdict.PASSED
        rec.state = S.MASTERED if passed else S.NOT_PASSED
        rec.attempts = (rec.attempts or 0) + 1
        score = float(result.total_score)
        rec.best_score = score if rec.best_score is None else max(float(rec.best_score), score)
        rec.last_session_id = result.session_id
        rec.prev_state = None
        if not passed:
            rec.last_failed_at = datetime.now(UTC)

        unlocked: list[str] = []
        if passed:
            done = {k for k, r in rows.items() if r.state in DONE}
            for child in t.children[key]:
                crec = rows[child]
                if crec.state == S.LOCKED and not t.missing(child, done):
                    crec.state = S.AVAILABLE
                    unlocked.append(child)
        self.db.flush()
        main = self._event(
            t,
            rec,
            key,
            state,
            R.SESSION_PASSED if passed else R.SESSION_FAILED,
            session_id=result.session_id,
            unlocked=[t.id_of[k] for k in unlocked],
        )
        changes.append(main)
        changes.extend(self._event(t, rows[k], k, S.LOCKED, R.UNLOCKED, session_id=result.session_id) for k in unlocked)
        self._commit(changes)
        return main

    # ------------------------------------------------------------------ sự kiện

    @staticmethod
    def _event(
        t: _Tree,
        rec: MasteryRecord,
        key: str,
        old: S | None,
        reason: R,
        *,
        session_id: UUID | None = None,
        unlocked: list[UUID] | None = None,
    ) -> MasteryChanged:
        return MasteryChanged(
            class_id=t.class_id,
            student_id=rec.student_id,
            node_id=t.id_of[key],
            node_key=key,
            old_state=old,
            new_state=S(rec.state),
            unlocked_node_ids=unlocked or [],
            session_id=session_id,
            reason=reason,
            version_id=t.schema.id,
        )

    def _commit(self, changes: list[MasteryChanged]) -> list[MasteryChanged]:
        """Commit rồi mới phát – bên nghe (heatmap, matching) đọc lại CSDL phải thấy dữ liệu mới.
        Lỗi kết nối khi phát (Redis rớt) không hoàn tác ma trận đã ghi: ghi log ERROR đủ ngữ cảnh.
        Sự kiện mất: heatmap được bù bởi task định kỳ `aggregation.reconcile_all` (C2-11).
        Lỗi khác (payload sai kiểu) vẫn ném."""
        self.db.commit()
        for ev in changes:
            try:
                self.bus.publish(TOPIC_MASTERY_CHANGED, ev)
            except (RedisError, OSError):
                log.exception(
                    "không phát được mastery.changed: lớp %s, SV %s, nút %s, %s → %s (%s)",
                    ev.class_id,
                    ev.student_id,
                    ev.node_key,
                    ev.old_state,
                    ev.new_state,
                    ev.reason,
                )
        return changes


_MESSAGES = {
    "NODE_LOCKED": "Nút còn khóa – cần Đạt các nút tiên quyết trước",
    "SESSION_IN_PROGRESS": "Bạn đang có phiên giảng ở nút này",
    "NODE_ALREADY_MASTERED": "Bạn đã Đạt nút này",
    "RETRY_COOLDOWN": f"Chờ {RETRY_COOLDOWN_MINUTES} phút rồi thử lại",
}


def register_handlers(bus: "EventBus", session_factory: Callable[[], Session] | None = None) -> None:
    """Nghe `session.completed` → `apply_result`. Gọi một lần ở tiến trình nghe sự kiện
    (`python -m app.workers.mastery_listener`)."""
    if session_factory is None:
        from app.db.session import SessionLocal

        session_factory = SessionLocal

    def on_session_completed(event: SessionResult) -> None:
        db = session_factory()
        try:
            changed = MasteryService(db, bus=bus).apply_result(event)
            if changed is not None and changed.unlocked_node_ids:
                # GET /sessions/{id}/result đọc ảnh chụp SessionResult trong Evaluation.feedback (bug #? –
                # unlockedNodes luôn [] vì ghi tại _finish trước khi MasteryService tính xong); vá lại ở đây.
                ev = db.scalar(select(Evaluation).where(Evaluation.session_id == event.session_id))
                if ev is not None and ev.feedback:
                    data = json.loads(ev.feedback)
                    data["unlockedNodes"] = [str(n) for n in changed.unlocked_node_ids]
                    ev.feedback = json.dumps(data)
                    db.commit()
        except Exception as exc:
            db.rollback()
            # Pub/Sub không lưu tin: log đủ để đối soát tay (bus chỉ ghi tên handler). TODO: đường đối soát / retry.
            log.exception(
                "apply_result lỗi – kết quả phiên %s CHƯA ghi vào ma trận: SV %s, nút %s, %s %.1f điểm%s",
                event.session_id,
                event.student_id,
                event.node_id,
                event.verdict,
                event.total_score,
                f", {exc.code} {exc.details}" if isinstance(exc, AppError) else "",
            )
            raise
        finally:
            db.close()

    bus.subscribe(TOPIC_SESSION_COMPLETED, on_session_completed)
