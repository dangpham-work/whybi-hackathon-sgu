"""Ghép cặp theo sự kiện trong hạn kiểm tra bài cũ của nút (C2-15, FR-PM-04). Chủ: Long.

GV đặt hạn (`NodeReviewWindow`) cho từng nút của lớp. Trong hạn, mỗi lần ô ma trận đổi (`mastery.changed`) hoặc beat
`live_rebalance` chạy, `rebalance_class` suy ra từ ma trận (không có bảng hàng chờ riêng):
  - người dạy: SV bật ghép cặp, đã Đạt nút, đang kèm < TEACH_LIMIT người học (cặp PROPOSED / WAITING_OTHER / ACCEPTED);
  - hàng chờ: SV bật ghép cặp, chưa Đạt nhưng đã trượt nút, chưa có cặp ở nút này.
rồi ghép đến-trước-phục-vụ-trước bằng `algorithms.live_matching.assign` (người học vào người dạy đang kèm ít nhất).
Hết hạn thì dừng ghép tự động; GV xem ai còn chờ ở `list_windows` và ghép tay.

Mỗi cặp là một PeerMatch (người dạy = A, người học = B, một mục dạy A → B) nên chấp nhận / học cùng / xác nhận lại
chạy như cũ. Vòng ghép của các cặp này có trigger_type = LIVE (một vòng chung cho cả lớp).
TODO(C2-19): NotificationService.notify cho hai SV khi có cặp.
"""

import logging
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.algorithms.live_matching import assign
from app.core.errors import AppError
from app.models.enums import MatchStatus
from app.models.peer import MatchingRound, NodeReviewWindow, PeerMatch, PeerMatchItem
from app.models.schemas.mastery import TOPIC_MASTERY_CHANGED, MasteryChanged
from app.models.schemas.matching import ReviewWindowOut
from app.models.users import ClassSection, Enrollment
from app.services.mastery import MasteryService
from app.services.matching import ACTIVE, NO_REPEAT, PENDING, PROPOSAL_TTL, MatchingService
from app.services.skill_tree import SkillTreeService

if TYPE_CHECKING:
    from app.api.deps import CurrentUser
    from app.realtime.bus import EventBus

log = logging.getLogger(__name__)

M = MatchStatus
LIVE = "LIVE"
TEACHING = (M.PROPOSED, M.WAITING_OTHER, M.ACCEPTED)  # cặp còn chiếm chỗ của người dạy


def _utcnow() -> datetime:
    return datetime.now(UTC)


class LiveMatching:
    def __init__(self, db: Session, now: Callable[[], datetime] = _utcnow) -> None:
        self.db = db
        self.now = now

    # ------------------------------------------------------------------ hạn kiểm tra (GV)

    def _owned_class(self, class_id: UUID, user: "CurrentUser") -> ClassSection:
        cls = self.db.scalar(select(ClassSection).where(ClassSection.id == class_id))
        if cls is None:
            raise AppError(404, "CLASS_NOT_FOUND", "Không tìm thấy lớp", {"classId": str(class_id)})
        MatchingService._require_owner(cls, user)
        return cls

    def set_window(self, class_id: UUID, node_id: UUID, deadline_at: datetime, user: "CurrentUser") -> ReviewWindowOut:
        """Đặt (hoặc dời) hạn kiểm tra bài cũ của nút; đặt xong chạy ngay một lượt ghép cho bạn đang chờ."""
        self._owned_class(class_id, user)
        tree = SkillTreeService(self.db).get_class_tree(class_id, user=None)
        node = next((n for n in tree.nodes if n.id == node_id), None)
        if node is None:
            raise AppError(404, "NODE_NOT_IN_TREE", "Nút không thuộc cây đang phát hành", {"nodeId": str(node_id)})
        if deadline_at.tzinfo is None:
            deadline_at = deadline_at.replace(tzinfo=UTC)
        if deadline_at <= self.now():
            raise AppError(
                422, "DEADLINE_IN_PAST", "Hạn kiểm tra phải ở tương lai", {"deadlineAt": deadline_at.isoformat()}
            )
        w = self.db.scalar(
            select(NodeReviewWindow).where(NodeReviewWindow.class_id == class_id, NodeReviewWindow.node_key == node.key)
        )
        if w is None:
            w = NodeReviewWindow(class_id=class_id, node_key=node.key, deadline_at=deadline_at)
            self.db.add(w)
        else:
            w.deadline_at = deadline_at
        self.db.commit()
        self.rebalance_class(class_id)
        return self._report(class_id, w)

    def list_windows(self, class_id: UUID, user: "CurrentUser") -> list[ReviewWindowOut]:
        self._owned_class(class_id, user)
        ws = self.db.scalars(
            select(NodeReviewWindow).where(NodeReviewWindow.class_id == class_id).order_by(NodeReviewWindow.deadline_at)
        )
        return [self._report(class_id, w) for w in ws]

    def open_class_ids(self) -> list[UUID]:
        """Lớp có ít nhất một hạn đang mở – beat `live_rebalance` chạy cho từng lớp."""
        q = select(NodeReviewWindow.class_id).where(NodeReviewWindow.deadline_at > self.now()).distinct()
        return list(self.db.scalars(q))

    # ------------------------------------------------------------------ suy ra hàng chờ / người dạy

    def _participants(self, class_id: UUID) -> set[UUID]:
        q = select(Enrollment.student_id).where(Enrollment.class_id == class_id, Enrollment.peer_opt_in.is_(True))
        return set(self.db.scalars(q))

    def _node_matches(self, class_id: UUID, key: str) -> list[tuple[PeerMatch, PeerMatchItem]]:
        """Cặp (kèm mục) của lớp ở nút `key` – so theo key vì cây có thể được phát hành lại."""
        rows = self.db.execute(
            select(PeerMatch, PeerMatchItem)
            .join(MatchingRound, MatchingRound.id == PeerMatch.round_id)
            .join(PeerMatchItem, PeerMatchItem.match_id == PeerMatch.id)
            .where(MatchingRound.class_id == class_id)
        ).all()
        keys = SkillTreeService(self.db).node_keys(list({item.node_id for _, item in rows}))
        return [(m, item) for m, item in rows if keys.get(item.node_id) == key]

    def _live_round(self, class_id: UUID) -> MatchingRound:
        rnd = self.db.scalar(
            select(MatchingRound)
            .where(MatchingRound.class_id == class_id, MatchingRound.trigger_type == LIVE)
            .order_by(MatchingRound.created_at.desc())
            .limit(1)
        )
        if rnd is None:
            rnd = MatchingRound(class_id=class_id, trigger_type=LIVE, algorithm="LIVE_FCFS", total_weight=0.0)
            self.db.add(rnd)
            self.db.flush()
        return rnd

    def _rebalance_node(self, class_id: UUID, key: str) -> int:
        out = MasteryService(self.db).node_outcomes(class_id, key)
        if out.node_id is None:
            return 0
        people = self._participants(class_id)
        rows = self._node_matches(class_id, key)
        now = self.now()

        passed = {s for s, _ in out.passed}
        for m, item in rows:  # bạn học đã Đạt thì không cần người dạy nữa
            if m.status in PENDING and item.learner_id in passed:
                m.status = M.DECLINED

        load = Counter(m.student_a_id for m, _ in rows if m.status in TEACHING)
        held = {item.learner_id for m, item in rows if m.status in ACTIVE}
        recent = {(m.student_a_id, m.student_b_id) for m, _ in rows if m.created_at and m.created_at >= now - NO_REPEAT}
        forbidden = {(str(a), str(b)) for a, b in recent} | {(str(b), str(a)) for a, b in recent}
        teachers = [(str(s), load[s]) for s, _ in out.passed if s in people]
        waiting = [str(s) for s, _ in out.failed if s in people and s not in held]

        pairs = assign(teachers, waiting, forbidden=forbidden)
        if not pairs:
            return 0
        rnd = self._live_round(class_id)
        for teacher, learner in pairs:
            m = PeerMatch(
                round_id=rnd.id,
                student_a_id=UUID(teacher),
                student_b_id=UUID(learner),
                weight=1.0,
                status=M.PROPOSED,
                accepted_by_a=False,
                accepted_by_b=False,
                studied_by_a=False,
                studied_by_b=False,
                expires_at=now + PROPOSAL_TTL,
            )
            self.db.add(m)
            self.db.flush()
            self.db.add(
                PeerMatchItem(match_id=m.id, teacher_id=UUID(teacher), learner_id=UUID(learner), node_id=out.node_id)
            )
        # TODO(C2-19): NotificationService.notify cho hai SV mỗi cặp
        return len(pairs)

    def rebalance_class(self, class_id: UUID) -> int:
        """Ghép bạn đang chờ với người dạy còn chỗ ở mọi nút còn hạn của lớp; trả số cặp mới. Khóa lớp nên hai lần
        chạy song song (sự kiện + beat) không ghép trùng; không có hạn nào đang mở thì không khóa gì."""
        now = self.now()
        windows = list(
            self.db.scalars(
                select(NodeReviewWindow).where(
                    NodeReviewWindow.class_id == class_id, NodeReviewWindow.deadline_at > now
                )
            )
        )
        if not windows:
            return 0
        self.db.scalar(select(ClassSection.id).where(ClassSection.id == class_id).with_for_update())
        made = sum(self._rebalance_node(class_id, w.node_key) for w in windows)
        self.db.commit()
        if made:
            log.info("ghép theo sự kiện lớp %s: %d cặp mới", class_id, made)
        return made

    # ------------------------------------------------------------------ báo cáo cho GV

    def _report(self, class_id: UUID, w: NodeReviewWindow) -> ReviewWindowOut:
        out = MasteryService(self.db).node_outcomes(class_id, w.node_key)
        people = self._participants(class_id)
        held = {item.learner_id for m, item in self._node_matches(class_id, w.node_key) if m.status in ACTIVE}
        waiting = [s for s, _ in out.failed if s in people and s not in held]
        message = None
        if waiting:
            message = f"{len(waiting)} bạn chưa có người dạy nút {w.node_key}. Hãy giảng trực tiếp hoặc ghép tay."
        return ReviewWindowOut(
            node_id=out.node_id,
            node_key=w.node_key,
            deadline_at=w.deadline_at,
            open=w.deadline_at > self.now(),
            teacher_count=sum(s in people for s, _ in out.passed),
            matched_count=len(held & {s for s, _ in out.failed}),
            waiting_student_ids=waiting,
            message=message,
        )


def register_handlers(bus: "EventBus", session_factory: Callable[[], Session] | None = None) -> None:
    """Nghe `mastery.changed` → `rebalance_class`. Gọi một lần ở tiến trình nghe sự kiện (mastery_listener).
    Nghe mastery.changed (không phải session.completed) để chắc ô ma trận đã cập nhật xong rồi mới ghép."""
    if session_factory is None:
        from app.db.session import SessionLocal

        session_factory = SessionLocal

    def on_mastery_changed(event: MasteryChanged) -> None:
        db = session_factory()
        try:
            LiveMatching(db).rebalance_class(event.class_id)
        except Exception:
            db.rollback()
            log.exception(
                "ghép theo sự kiện lỗi – lớp %s, SV %s, nút %s; beat live_rebalance sẽ thử lại",
                event.class_id,
                event.student_id,
                event.node_key,
            )
            raise
        finally:
            db.close()

    bus.subscribe(TOPIC_MASTERY_CHANGED, on_mastery_changed)
