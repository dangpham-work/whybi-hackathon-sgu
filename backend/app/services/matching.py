"""MatchingService – Vòng ghép cặp, phản hồi gợi ý, xác nhận lại (UC15, UC22, UC23). Chủ: Long (C2-14, C2-15).

- Ma trận thành thạo chỉ ĐỌC qua `MasteryService.matching_snapshot` (không đụng `mastery_records`).
- Trạng thái theo Hình 4.30; `expires_at` là hạn của trạng thái hiện tại (BR-09):
  PROPOSED / WAITING_OTHER: 48 giờ từ lúc gợi ý · ACCEPTED: 7 ngày để học cùng · STUDIED: 7 ngày để xác nhận lại.
- Hết hạn: beat `expire_matches` (5 phút) gọi `expire_due`; phản hồi sau hạn cũng tự chuyển EXPIRED (409 MATCH_EXPIRED).
- Xác nhận lại: nghe `session.completed` (SessionResult) – phiên Đạt của người học ở đúng nút ⇒ mục verified;
  đủ mọi mục ⇒ VERIFIED. Hết 7 ngày: có mục Đạt ⇒ PARTIALLY_VERIFIED, không ⇒ UNVERIFIED.
- TODO(C2-19): gửi thông báo cho hai SV khi có gợi ý / khi cả hai chấp nhận (NotificationService chưa có).
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.algorithms.matching import _top, complementarity, node_priority
from app.algorithms.matching import run_round as solve_round
from app.core.errors import AppError
from app.models import tree as tree_orm
from app.models.enums import MatchStatus, Role, Verdict
from app.models.peer import MatchingRound, NodeReviewWindow, PeerMatch, PeerMatchItem
from app.models.schemas.mastery import TOPIC_SESSION_COMPLETED
from app.models.schemas.matching import MatchAdjust, MatchingStats, MatchItemOut, MatchOut, RoundOut
from app.models.schemas.session import SessionResult
from app.models.users import ClassSection, Enrollment, User
from app.services.mastery import MasteryService
from app.services.skill_tree import SkillTreeService

if TYPE_CHECKING:
    from app.api.deps import CurrentUser
    from app.realtime.bus import EventBus

log = logging.getLogger(__name__)

M = MatchStatus
PROPOSAL_TTL = timedelta(hours=48)  # BR-09
STUDY_TTL = timedelta(days=7)  # ACCEPTED → STUDIED
VERIFY_TTL = timedelta(days=7)  # BR-09: hạn xác nhận lại sau khi học cùng
NO_REPEAT = timedelta(days=14)  # BR-08: không ghép lại cùng cặp trong N ngày
ACTIVE = (M.PROPOSED, M.WAITING_OTHER, M.ACCEPTED, M.STUDIED)
PENDING = (M.PROPOSED, M.WAITING_OTHER)


def _rate(num: int, den: int) -> float:
    return round(num / den, 4) if den else 0.0


def _utcnow() -> datetime:
    return datetime.now(UTC)


class MatchingService:
    def __init__(self, db: Session, now: Callable[[], datetime] = _utcnow) -> None:
        self.db = db
        self.now = now

    # ------------------------------------------------------------------ quyền, nạp

    def _class(self, class_id: UUID, *, lock: bool = False) -> ClassSection:
        q = select(ClassSection).where(ClassSection.id == class_id)
        cls = self.db.scalar(q.with_for_update() if lock else q)
        if cls is None:
            raise AppError(404, "CLASS_NOT_FOUND", "Không tìm thấy lớp", {"classId": str(class_id)})
        return cls

    @staticmethod
    def _require_owner(cls: ClassSection, user: "CurrentUser") -> None:
        if user.role != Role.LECTURER or cls.lecturer_id != user.id:
            raise AppError(403, "NOT_CLASS_OWNER", "Chỉ GV phụ trách lớp được thao tác")

    def _match(self, match_id: UUID, user: "CurrentUser") -> PeerMatch:
        m = self.db.scalar(select(PeerMatch).where(PeerMatch.id == match_id).with_for_update())
        if m is None:
            raise AppError(404, "MATCH_NOT_FOUND", "Không tìm thấy gợi ý ghép cặp", {"matchId": str(match_id)})
        if user.id not in (m.student_a_id, m.student_b_id):
            raise AppError(403, "NOT_MATCH_MEMBER", "Bạn không thuộc cặp này")
        return m

    # ------------------------------------------------------------------ bật / tắt (FR-PM-01, BR-10)

    def set_opt_in(self, enrollment_id: UUID, user: "CurrentUser", opt_in: bool) -> bool:
        e = self.db.scalar(select(Enrollment).where(Enrollment.id == enrollment_id).with_for_update())
        if e is None:
            raise AppError(404, "ENROLLMENT_NOT_FOUND", "Không tìm thấy ghi danh", {"enrollmentId": str(enrollment_id)})
        if e.student_id != user.id:
            raise AppError(403, "FORBIDDEN", "Đây không phải ghi danh của bạn")
        e.peer_opt_in = opt_in
        if not opt_in:
            # BR-10: tắt tham gia ⇒ từ chối mọi gợi ý đang chờ của SV ở lớp này
            pending = self.db.scalars(
                select(PeerMatch)
                .join(MatchingRound, MatchingRound.id == PeerMatch.round_id)
                .where(
                    MatchingRound.class_id == e.class_id,
                    PeerMatch.status.in_(PENDING),
                    (PeerMatch.student_a_id == user.id) | (PeerMatch.student_b_id == user.id),
                )
                .with_for_update(of=PeerMatch)
            )
            for m in pending:
                m.status = M.DECLINED
        self.db.commit()
        return opt_in

    # ------------------------------------------------------------------ vòng ghép (UC15)

    def _class_matches(self, class_id: UUID):
        return (
            select(PeerMatch)
            .join(MatchingRound, MatchingRound.id == PeerMatch.round_id)
            .where(MatchingRound.class_id == class_id)
        )

    def run_round(
        self,
        class_id: UUID,
        trigger: str,
        user: "CurrentUser | None" = None,
        priority_node_id: UUID | None = None,
    ) -> RoundOut:
        """trigger = MANUAL (GV, `user` bắt buộc) hoặc SCHEDULED (beat). Commit rồi trả kết quả."""
        cls = self._class(class_id, lock=True)  # khóa lớp: hai vòng song song không ghép trùng SV
        if trigger == "MANUAL":
            if user is None:
                raise AppError(403, "NOT_CLASS_OWNER", "Chỉ GV phụ trách lớp được chạy vòng ghép")
            self._require_owner(cls, user)
        matrix = MasteryService(self.db).matching_snapshot(class_id)
        now = self.now()
        priority_key = None
        if priority_node_id is not None:
            priority_key = next((k for k, i in matrix.id_of.items() if i == priority_node_id), None)
            if priority_key is None:
                raise AppError(
                    404, "NODE_NOT_IN_TREE", "Nút không thuộc cây đang phát hành", {"nodeId": str(priority_node_id)}
                )

        busy: set[UUID] = set()
        recent: set[frozenset[str]] = set()
        for m in self.db.scalars(self._class_matches(class_id)):
            if m.status in ACTIVE:
                busy |= {m.student_a_id, m.student_b_id}
            if m.created_at is not None and m.created_at >= now - NO_REPEAT:
                recent.add(frozenset((str(m.student_a_id), str(m.student_b_id))))

        opted = self.db.scalars(
            select(Enrollment.student_id)
            .where(Enrollment.class_id == class_id, Enrollment.peer_opt_in.is_(True))
            .order_by(Enrollment.student_id)
        )
        participants = [s for s in opted if s not in busy]
        if len(participants) < 2:
            raise AppError(
                409,
                "NOT_ENOUGH_PARTICIPANTS",
                "Cần ít nhất 2 SV bật ghép cặp và chưa có cặp đang hoạt động",
                {"participantCount": len(participants)},
            )

        keys = [str(s) for s in participants]
        pairs, waiting = solve_round(
            keys,
            {str(s): matrix.mastered.get(s, set()) for s in participants},
            {str(s): matrix.frontier.get(s, set()) for s in participants},
            matrix.pass_rate,
            recent,
            priority_node=priority_key,
        )
        rnd = MatchingRound(
            class_id=class_id,
            trigger_type=trigger,
            triggered_by=user.id if user is not None else None,
            algorithm="BLOSSOM",
            participant_count=len(participants),
            total_weight=sum(p.weight for p in pairs),
        )
        self.db.add(rnd)
        self.db.flush()
        created: list[PeerMatch] = []
        for p in pairs:
            a, b = UUID(p.a), UUID(p.b)
            m = PeerMatch(
                round_id=rnd.id,
                student_a_id=a,
                student_b_id=b,
                weight=p.weight,
                status=M.PROPOSED,
                accepted_by_a=False,
                accepted_by_b=False,
                studied_by_a=False,
                studied_by_b=False,
                expires_at=now + PROPOSAL_TTL,
            )
            self.db.add(m)
            self.db.flush()
            for teacher, learner, nodes in ((a, b, p.a_teaches), (b, a, p.b_teaches)):
                for key in nodes:
                    self.db.add(
                        PeerMatchItem(match_id=m.id, teacher_id=teacher, learner_id=learner, node_id=matrix.id_of[key])
                    )
            created.append(m)
        self.db.flush()
        out = RoundOut(
            id=rnd.id,
            trigger_type=trigger,
            participant_count=len(participants),
            total_weight=float(rnd.total_weight or 0.0),
            matches=self._out(created, viewer=None),
            waiting_student_ids=[UUID(s) for s in waiting],
            created_at=rnd.created_at or now,
        )
        self.db.commit()
        log.info(
            "vòng ghép %s lớp %s (%s): %d SV, %d cặp, %d chờ",
            rnd.id,
            class_id,
            trigger,
            len(participants),
            len(created),
            len(waiting),
        )
        # TODO(C2-19): NotificationService.notify cho hai SV mỗi cặp
        return out

    def scheduled_class_ids(self) -> list[UUID]:
        """Lớp đã phát hành cây và có ≥ 2 SV bật ghép cặp – beat `scheduled_rounds` chạy vòng cho từng lớp."""
        # C2-15: lớp đang có hạn kiểm tra mở ghép theo sự kiện, không ghép lô chen vào
        live = select(NodeReviewWindow.class_id).where(NodeReviewWindow.deadline_at > self.now())
        q = (
            select(Enrollment.class_id)
            .join(tree_orm.SkillTree, tree_orm.SkillTree.class_id == Enrollment.class_id)
            .where(
                Enrollment.peer_opt_in.is_(True),
                tree_orm.SkillTree.published_version_id.is_not(None),
                Enrollment.class_id.not_in(live),
            )
            .group_by(Enrollment.class_id)
            .having(func.count() >= 2)
        )
        return list(self.db.scalars(q))

    # ------------------------------------------------------------------ đọc

    def list_matches(self, class_id: UUID, user: "CurrentUser") -> list[MatchOut]:
        cls = self._class(class_id)
        q = self._class_matches(class_id).order_by(PeerMatch.created_at.desc(), PeerMatch.id)
        if user.role == Role.STUDENT:
            enrolled = self.db.scalar(
                select(Enrollment.id).where(Enrollment.class_id == class_id, Enrollment.student_id == user.id)
            )
            if enrolled is None:
                raise AppError(403, "NOT_ENROLLED", "Bạn chưa tham gia lớp này")
            q = q.where((PeerMatch.student_a_id == user.id) | (PeerMatch.student_b_id == user.id))
            return self._out(list(self.db.scalars(q)), viewer=user.id)
        self._require_owner(cls, user)
        return self._out(list(self.db.scalars(q)), viewer=None)

    def _out(self, matches: list[PeerMatch], viewer: UUID | None) -> list[MatchOut]:
        if not matches:
            return []
        ids = [m.id for m in matches]
        items: dict[UUID, list[PeerMatchItem]] = {i: [] for i in ids}
        for it in self.db.scalars(
            select(PeerMatchItem).where(PeerMatchItem.match_id.in_(ids)).order_by(PeerMatchItem.id)
        ):
            items[it.match_id].append(it)
        node_key = SkillTreeService(self.db).node_keys(list({it.node_id for lst in items.values() for it in lst}))
        people = {m.student_a_id for m in matches} | {m.student_b_id for m in matches}
        users = {u.id: u for u in self.db.scalars(select(User).where(User.id.in_(people)))}
        out: list[MatchOut] = []
        for m in matches:
            me_is_b = viewer == m.student_b_id
            me, partner = (m.student_b_id, m.student_a_id) if me_is_b else (m.student_a_id, m.student_b_id)
            its = items[m.id]
            shared = m.status not in (M.PROPOSED, M.WAITING_OTHER, M.DECLINED, M.EXPIRED)
            out.append(
                MatchOut(
                    id=m.id,
                    partner_id=partner,
                    partner_name=users[partner].full_name,
                    partner_email=users[partner].email if shared else None,
                    i_teach=[node_key[i.node_id] for i in its if i.teacher_id == me],
                    i_learn=[node_key[i.node_id] for i in its if i.learner_id == me],
                    status=M(m.status),
                    weight=float(m.weight),
                    expires_at=m.expires_at,
                    one_way=not any(i.teacher_id == m.student_b_id for i in its),
                    accepted_by_me=m.accepted_by_b if me_is_b else m.accepted_by_a,
                    studied_by_me=m.studied_by_b if me_is_b else m.studied_by_a,
                    student_a_id=m.student_a_id,
                    student_a_name=users[m.student_a_id].full_name,
                    student_b_id=m.student_b_id,
                    student_b_name=users[m.student_b_id].full_name,
                    items=[
                        MatchItemOut(
                            id=i.id,
                            teacher_id=i.teacher_id,
                            learner_id=i.learner_id,
                            node_id=i.node_id,
                            node_key=node_key[i.node_id],
                            verified=i.verified,
                            verified_at=i.verified_at,
                        )
                        for i in its
                    ],
                    created_at=m.created_at,
                )
            )
        return out

    # ------------------------------------------------------------------ GV điều chỉnh, thống kê (C2-15)

    def adjust_match(self, match_id: UUID, user: "CurrentUser", body: MatchAdjust) -> MatchOut:
        """FR-PM-08: GV hủy cặp (⇒ DECLINED) hoặc thay một SV. Cặp mới tính lại nút dạy / học từ ma trận hiện tại,
        quay về PROPOSED (hai bên chấp nhận lại, hạn 48 giờ). Hai SV không có gì để dạy nhau ⇒ 422."""
        m = self.db.scalar(select(PeerMatch).where(PeerMatch.id == match_id).with_for_update())
        if m is None:
            raise AppError(404, "MATCH_NOT_FOUND", "Không tìm thấy gợi ý ghép cặp", {"matchId": str(match_id)})
        class_id = self.db.scalar(select(MatchingRound.class_id).where(MatchingRound.id == m.round_id))
        self._require_owner(self._class(class_id), user)
        if m.status not in ACTIVE:
            self._invalid(m)
        if body.cancel:
            m.status = M.DECLINED
            self.db.commit()
            return self._out([m], viewer=None)[0]

        old, new = body.replace_student_id, body.with_student_id
        if old not in (m.student_a_id, m.student_b_id):
            raise AppError(422, "REPLACE_NOT_IN_MATCH", "SV cần thay không thuộc cặp này")
        other = m.student_b_id if old == m.student_a_id else m.student_a_id
        if new in (old, other):
            raise AppError(422, "REPLACE_NOT_IN_MATCH", "SV thay thế phải khác hai SV hiện tại")
        enr = self.db.scalar(select(Enrollment).where(Enrollment.class_id == class_id, Enrollment.student_id == new))
        if enr is None:
            raise AppError(404, "STUDENT_NOT_IN_CLASS", "SV thay thế chưa tham gia lớp", {"studentId": str(new)})
        if not enr.peer_opt_in:
            raise AppError(409, "STUDENT_NOT_OPTED_IN", "SV thay thế chưa bật ghép cặp (BR-10)")
        busy = self.db.scalar(
            self._class_matches(class_id).where(
                PeerMatch.id != m.id,
                PeerMatch.status.in_(ACTIVE),
                (PeerMatch.student_a_id == new) | (PeerMatch.student_b_id == new),
            )
        )
        if busy is not None:
            raise AppError(409, "STUDENT_BUSY", "SV thay thế đang trong một cặp hoạt động khác")

        snap = MasteryService(self.db).matching_snapshot(class_id)
        p = node_priority(snap.pass_rate)
        a, b = (new, other) if old == m.student_a_id else (other, new)
        t_ab = snap.mastered.get(a, set()) & snap.frontier.get(b, set())
        t_ba = snap.mastered.get(b, set()) & snap.frontier.get(a, set())
        if not t_ab and not t_ba:
            raise AppError(422, "NO_COMPLEMENTARY_NODES", "Hai SV không có nút nào để dạy nhau")
        if not t_ab:  # chỉ một chiều ⇒ người dạy luôn là A (quy ước ghép một chiều)
            a, b, t_ab, t_ba = b, a, t_ba, set()
        m.student_a_id, m.student_b_id = a, b
        m.weight = complementarity(str(a), str(b), {str(a): snap.mastered[a], str(b): snap.mastered[b]},
                                   {str(a): snap.frontier[a], str(b): snap.frontier[b]}, p) or sum(
            p.get(n, 1.0) for n in _top(t_ab, p, 2)
        )  # fmt: skip
        m.status = M.PROPOSED
        m.accepted_by_a = m.accepted_by_b = m.studied_by_a = m.studied_by_b = False
        m.expires_at = self.now() + PROPOSAL_TTL
        self.db.execute(delete(PeerMatchItem).where(PeerMatchItem.match_id == m.id))
        for teacher, learner, nodes in ((a, b, t_ab), (b, a, t_ba)):
            for key in _top(nodes, p, 2):
                self.db.add(
                    PeerMatchItem(match_id=m.id, teacher_id=teacher, learner_id=learner, node_id=snap.id_of[key])
                )
        self.db.commit()
        return self._out([m], viewer=None)[0]

    def stats(self, class_id: UUID, user: "CurrentUser") -> MatchingStats:
        """Mục 6.6.6: tỉ lệ chấp nhận gợi ý, tỉ lệ cặp học cùng, tỉ lệ mục được xác nhận Đạt (chỉ GV phụ trách lớp)."""
        self._require_owner(self._class(class_id), user)
        matches = list(self.db.scalars(self._class_matches(class_id)))
        accepted = [m for m in matches if m.accepted_by_a and m.accepted_by_b]
        studied = [m for m in matches if m.studied_by_a and m.studied_by_b]
        items = list(
            self.db.scalars(select(PeerMatchItem).where(PeerMatchItem.match_id.in_([m.id for m in studied])))
        ) if studied else []  # fmt: skip
        verified = sum(1 for i in items if i.verified)
        return MatchingStats(
            total_matches=len(matches),
            accepted=len(accepted),
            declined=sum(m.status == M.DECLINED for m in matches),
            expired=sum(m.status == M.EXPIRED for m in matches),
            studied=len(studied),
            items_total=len(items),
            items_verified=verified,
            accept_rate=_rate(len(accepted), len(matches)),
            studied_rate=_rate(len(studied), len(accepted)),
            verified_rate=_rate(verified, len(items)),
        )

    # ------------------------------------------------------------------ phản hồi (UC22)

    def respond(self, match_id: UUID, user: "CurrentUser", action: str) -> MatchOut:
        """action ∈ accept | decline | studied. Bấm lặp an toàn (trả trạng thái hiện tại)."""
        m = self._match(match_id, user)
        now = self.now()
        is_a = user.id == m.student_a_id
        if m.status in (*PENDING, M.ACCEPTED, M.STUDIED) and m.expires_at <= now:
            self._expire(m)
            self.db.commit()
            raise AppError(409, "MATCH_EXPIRED", "Gợi ý ghép cặp đã hết hạn", {"status": m.status})

        if action == "accept":
            if m.status in PENDING:
                if is_a:
                    m.accepted_by_a = True
                else:
                    m.accepted_by_b = True
                if m.accepted_by_a and m.accepted_by_b:
                    m.status = M.ACCEPTED
                    m.expires_at = now + STUDY_TTL
                    # TODO(C2-19): báo hai SV thông tin liên hệ của nhau
                else:
                    m.status = M.WAITING_OTHER
            elif not (m.status == M.ACCEPTED):
                self._invalid(m)
        elif action == "decline":
            if m.status in PENDING:
                m.status = M.DECLINED
            elif m.status != M.DECLINED:
                self._invalid(m)
        elif action == "studied":
            if m.status == M.ACCEPTED:
                if is_a:
                    m.studied_by_a = True
                else:
                    m.studied_by_b = True
                if m.studied_by_a and m.studied_by_b:
                    m.status = M.STUDIED
                    m.expires_at = now + VERIFY_TTL  # mở yêu cầu xác nhận lại (UC23)
            elif m.status != M.STUDIED:
                self._invalid(m)
        else:
            raise AppError(422, "INVALID_ACTION", "Thao tác không hợp lệ", {"action": action})
        self.db.flush()
        out = self._out([m], viewer=user.id)[0]
        self.db.commit()
        return out

    @staticmethod
    def _invalid(m: PeerMatch) -> None:
        raise AppError(409, "MATCH_INVALID_STATE", "Không thể thao tác ở trạng thái hiện tại", {"status": m.status})

    # ------------------------------------------------------------------ hết hạn (BR-09)

    def _expire(self, m: PeerMatch) -> None:
        if m.status in (*PENDING, M.ACCEPTED):
            m.status = M.EXPIRED
        elif m.status == M.STUDIED:
            flags = list(self.db.scalars(select(PeerMatchItem.verified).where(PeerMatchItem.match_id == m.id)))
            if flags and all(flags):
                m.status = M.VERIFIED
            elif any(flags):
                m.status = M.PARTIALLY_VERIFIED
            else:
                m.status = M.UNVERIFIED

    def expire_due(self, now: datetime | None = None) -> dict[str, int]:
        """Chuyển mọi cặp quá hạn sang trạng thái kết thúc. Bỏ qua dòng đang bị khóa (SV đang phản hồi)."""
        now = now or self.now()
        counts = {s: 0 for s in (M.EXPIRED, M.VERIFIED, M.PARTIALLY_VERIFIED, M.UNVERIFIED)}
        due = self.db.scalars(
            select(PeerMatch)
            .where(PeerMatch.status.in_((*PENDING, M.ACCEPTED, M.STUDIED)), PeerMatch.expires_at <= now)
            .with_for_update(skip_locked=True)
        )
        for m in due:
            self._expire(m)
            counts[M(m.status)] += 1
        self.db.commit()
        if any(counts.values()):
            log.info("hết hạn ghép cặp: %s", counts)
        return {str(k): v for k, v in counts.items()}

    # ------------------------------------------------------------------ xác nhận lại (UC23, FR-PM-07)

    def check_followup_item(self, student_id: UUID, node_id: UUID, item_id: UUID) -> None:
        """Mở phiên xác nhận lại: mục phải là của chính người học, cặp đang STUDIED còn hạn, cùng key nút."""
        row = self.db.execute(
            select(PeerMatchItem, PeerMatch)
            .join(PeerMatch, PeerMatch.id == PeerMatchItem.match_id)
            .where(PeerMatchItem.id == item_id)
        ).first()
        if row is None or row[0].learner_id != student_id:
            raise AppError(403, "FORBIDDEN", "Mục ghép cặp này không phải của bạn")
        it, m = row
        if m.status != M.STUDIED or m.expires_at <= self.now() or it.verified:
            raise AppError(409, "MATCH_INVALID_STATE", "Mục ghép cặp không còn chờ xác nhận lại", {"status": m.status})
        keys = SkillTreeService(self.db).node_keys([node_id, it.node_id])
        if keys.get(node_id) is None or keys.get(node_id) != keys.get(it.node_id):
            raise AppError(422, "PEER_ITEM_NODE_MISMATCH", "Phiên xác nhận lại phải ở đúng nút của mục ghép cặp")

    def verify_from_session(self, result: SessionResult) -> bool:
        """Phiên Đạt của người học ở đúng nút của một mục (cặp đang STUDIED) ⇒ mục verified; đủ ⇒ VERIFIED.
        Trả True nếu có mục vừa được xác nhận. Gửi lặp / phiên không liên quan ⇒ False."""
        if result.verdict != Verdict.PASSED or not (result.is_peer_followup or result.peer_match_item_id):
            return False
        # Phiên phải kết thúc trước hạn 7 ngày của cặp (BR-09) và thuộc đúng lớp của vòng ghép
        done_at = result.completed_at or self.now()
        q = (
            select(PeerMatchItem)
            .join(PeerMatch, PeerMatch.id == PeerMatchItem.match_id)
            .join(MatchingRound, MatchingRound.id == PeerMatch.round_id)
            .where(
                PeerMatchItem.learner_id == result.student_id,
                PeerMatchItem.verified.is_(False),
                PeerMatch.status == M.STUDIED,
                PeerMatch.expires_at > done_at,
                MatchingRound.class_id == result.class_id,
            )
        )
        if result.peer_match_item_id is not None:
            q = q.where(PeerMatchItem.id == result.peer_match_item_id)
        candidates = list(self.db.scalars(q.with_for_update(of=PeerMatchItem)))
        # So theo key: phiên có thể chạy ở phiên bản cây mới hơn lúc ghép
        keys = SkillTreeService(self.db).node_keys([result.node_id, *(c.node_id for c in candidates)])
        target = keys.get(result.node_id)
        hit = next((c for c in candidates if target is not None and keys.get(c.node_id) == target), None)
        if hit is None:
            self.db.commit()  # chỉ nhả khóa dòng, không có thay đổi
            return False
        hit.verified = True
        hit.verified_at = self.now()
        self.db.flush()
        m = self.db.scalar(select(PeerMatch).where(PeerMatch.id == hit.match_id).with_for_update())
        flags = list(self.db.scalars(select(PeerMatchItem.verified).where(PeerMatchItem.match_id == m.id)))
        if all(flags):
            m.status = M.VERIFIED
        self.db.commit()
        log.info("xác nhận lại mục %s (cặp %s, phiên %s) ⇒ cặp %s", hit.id, m.id, result.session_id, m.status)
        return True


def register_handlers(bus: "EventBus", session_factory: Callable[[], Session] | None = None) -> None:
    """Nghe `session.completed` → `verify_from_session`. Gọi một lần ở tiến trình nghe sự kiện (mastery_listener)."""
    if session_factory is None:
        from app.db.session import SessionLocal

        session_factory = SessionLocal

    def on_session_completed(event: SessionResult) -> None:
        if not (event.is_peer_followup or event.peer_match_item_id):
            return
        db = session_factory()
        try:
            MatchingService(db).verify_from_session(event)
        except Exception:
            db.rollback()
            log.exception(
                "verify_from_session lỗi – phiên %s CHƯA xác nhận mục ghép cặp %s: SV %s, nút %s, %s",
                event.session_id,
                event.peer_match_item_id,
                event.student_id,
                event.node_id,
                event.verdict,
            )
            raise
        finally:
            db.close()

    bus.subscribe(TOPIC_SESSION_COMPLETED, on_session_completed)
