"""C2-14 – Xong khi: Ví dụ 6.6.4 ra đúng cặp; gợi ý quá 48 giờ tự hết hạn; xác nhận lại Đạt thì cặp "đã xác nhận".

Cần Postgres đã migrate (TEST_DATABASE_URL). Dùng lại World / cây mẫu của C2-09 và MasteryService (C2-10).
Ma trận dựng trên cây mẫu theo tinh thần Hình 6.11 (mọi SV đã Đạt N1, N3 nên N2, N4, N5 là Biên):
  An Đạt N2, N5 · Châu Đạt N2, N4 · Hà chưa Đạt thêm · Dũng Đạt N2, N4, N5 · Khang chỉ Đạt N1 và TẮT ghép cặp.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.models.enums import MasteryState, MatchStatus, Role, Verdict
from app.models.peer import PeerMatch, PeerMatchItem
from app.models.schemas.mastery import TOPIC_SESSION_COMPLETED
from app.models.schemas.session import SessionResult
from app.models.session import TeachingSession
from app.models.users import ClassSection, Enrollment, Student, User
from app.realtime.bus import InMemoryEventBus
from app.services.mastery import MasteryService
from app.services.matching import MatchingService
from app.services.matching import register_handlers as register_matching
from tests.unit import test_tree_edit_db as _c209
from tests.unit.test_tree_edit_db import DB_URL, _approve_all, _import_seed

world = _c209.world

pytestmark = pytest.mark.skipif(not DB_URL, reason="đặt TEST_DATABASE_URL để chạy trên Postgres thật")

N1, N2, N3, N4, N5, N6 = (
    "n1_bien_bo_nho",
    "n2_mang",
    "n3_ham_tham_so",
    "n4_de_quy",
    "n5_con_tro",
    "n6_cap_phat_dong",
)
PLAN = {
    "An": ([N1, N3, N2, N5], True),
    "Chau": ([N1, N3, N2, N4], True),
    "Ha": ([N1, N3], True),
    "Dung": ([N1, N3, N2, N4, N5], True),
    "Khang": ([N1], False),
}


class _NoClose:
    """Phiên CSDL của test cho handler / task dùng chung: bỏ qua close() (đóng sẽ tách đối tượng của request)."""

    def __init__(self, db):
        self._db = db

    def __getattr__(self, name):
        return getattr(self._db, name)

    def close(self):
        pass


@pytest.fixture
def bus(monkeypatch):
    import app.services.mastery as mastery_mod
    import app.services.session_orchestrator as orch_mod

    b = InMemoryEventBus()
    monkeypatch.setattr(mastery_mod, "get_bus", lambda: b)
    monkeypatch.setattr(orch_mod, "get_bus", lambda: b)
    return b


class Klass:
    """Lớp đã phát hành cây mẫu, 5 SV theo PLAN."""

    def __init__(self, w, tree, bus):
        self.w, self.tree, self.bus = w, tree, bus
        self.db = w.db
        self.ids: dict[str, UUID] = {}
        self.enrollment: dict[str, UUID] = {}
        svc = MasteryService(w.db, bus=bus)
        for name, (keys, opt_in) in PLAN.items():
            u = User(
                id=uuid4(), full_name=name, email=f"{name.lower()}.{uuid4().hex[:6]}@whybi.test", password_hash="x"
            )
            u.role = Role.STUDENT
            w.db.add(u)
            w.db.flush()
            w.db.add(Student(user_id=u.id, student_code=uuid4().hex[:10]))
            w.db.flush()
            e = Enrollment(class_id=w.class_id, student_id=u.id, peer_opt_in=opt_in)
            w.db.add(e)
            w.db.flush()
            self.ids[name], self.enrollment[name] = u.id, e.id
            w.roles[u.id] = Role.STUDENT
            svc.ensure_student(w.class_id, u.id)
            for k in keys:
                sid = uuid4()
                w.db.add(
                    TeachingSession(
                        id=sid,
                        student_id=u.id,
                        node_id=self.node(k),
                        class_id=w.class_id,
                        input_mode="TEXT",
                        status="CREATED",
                    )
                )
                w.db.flush()
                svc.start_session(u.id, self.node(k), sid)
                svc.apply_result(
                    SessionResult(
                        session_id=sid,
                        student_id=u.id,
                        node_id=self.node(k),
                        class_id=w.class_id,
                        state=MasteryState.MASTERED,
                        verdict=Verdict.PASSED,
                        total_score=90,
                        criteria=[],
                    )
                )
        self.name_of = {v: k for k, v in self.ids.items()}

    def node(self, key: str) -> UUID:
        return UUID(next(n["id"] for n in self.tree["nodes"] if n["key"] == key))

    def as_(self, name: str):
        self.w.current = self.ids[name] if name in self.ids else getattr(self.w, name)
        return self.w.api

    def run_round(self):
        r = self.as_("gv").post(f"/api/v1/classes/{self.w.class_id}/matching-rounds", json={})
        assert r.status_code == 201, r.text
        return r.json()

    def match_of(self, round_body: dict, name: str) -> dict:
        sid = str(self.ids[name])
        return next(m for m in round_body["matches"] if sid in (m["studentAId"], m["studentBId"]))

    def act(self, name: str, match_id: str, action: str):
        return self.as_(name).post(f"/api/v1/matches/{match_id}/{action}")


@pytest.fixture
def k(world, bus):
    tv = _import_seed(world)
    _approve_all(world, tv)
    r = world.api.post(f"/api/v1/tree-versions/{tv['id']}/publish")
    assert r.status_code == 200, r.text
    return Klass(world, r.json(), bus)


def two_way(k: Klass) -> str:
    rnd = k.run_round()
    return k.match_of(rnd, "An")["id"]


def to_studied(k: Klass) -> str:
    mid = two_way(k)
    for name in ("An", "Chau"):
        assert k.act(name, mid, "accept").status_code == 200
    for name in ("An", "Chau"):
        assert k.act(name, mid, "studied").status_code == 200
    return mid


def item(k: Klass, mid: str, learner: str) -> PeerMatchItem:
    return k.db.scalar(
        select(PeerMatchItem).where(PeerMatchItem.match_id == UUID(mid), PeerMatchItem.learner_id == k.ids[learner])
    )


def status(k: Klass, mid: str) -> str:
    k.db.expire_all()
    return k.db.get(PeerMatch, UUID(mid)).status


# --- Vòng ghép (UC15, Xong khi 1) ----------------------------------------------------------------


def test_round_example_6_6_4(k):
    before = datetime.now(UTC)
    rnd = k.run_round()
    assert rnd["participantCount"] == 4, "Khang tắt ghép cặp, SV mặc định của World chưa bật"
    assert rnd["triggerType"] == "MANUAL" and rnd["waitingStudentIds"] == []
    assert len(rnd["matches"]) == 2

    ac = k.match_of(rnd, "An")
    assert {k.name_of[UUID(ac["studentAId"])], k.name_of[UUID(ac["studentBId"])]} == {"An", "Chau"}
    assert ac["oneWay"] is False and ac["status"] == "PROPOSED"
    teach = {(k.name_of[UUID(i["teacherId"])], i["nodeKey"]) for i in ac["items"]}
    assert teach == {("An", N5), ("Chau", N4)}, "An dạy N5, Châu dạy N4"
    expires = datetime.fromisoformat(ac["expiresAt"])
    assert timedelta(hours=47) < expires - before <= timedelta(hours=48, minutes=1)

    dh = k.match_of(rnd, "Ha")
    assert dh["oneWay"] is True
    assert {k.name_of[UUID(i["teacherId"])] for i in dh["items"]} == {"Dung"}
    assert {k.name_of[UUID(i["learnerId"])] for i in dh["items"]} == {"Ha"}
    assert {i["nodeKey"] for i in dh["items"]} <= {N2, N4, N5} and len(dh["items"]) == 2
    assert rnd["totalWeight"] == pytest.approx(sum(m["weight"] for m in rnd["matches"]))


def test_round_permissions(k):
    k.w.current = k.w.gv_other
    r = k.w.api.post(f"/api/v1/classes/{k.w.class_id}/matching-rounds", json={})
    assert r.status_code == 403 and r.json()["error"]["code"] == "NOT_CLASS_OWNER"
    r = k.as_("An").post(f"/api/v1/classes/{k.w.class_id}/matching-rounds", json={})
    assert r.status_code == 403


def test_students_with_active_match_are_not_rematched(k):
    k.run_round()
    r = k.as_("gv").post(f"/api/v1/classes/{k.w.class_id}/matching-rounds", json={})
    assert r.status_code == 409 and r.json()["error"]["code"] == "NOT_ENOUGH_PARTICIPANTS"


def test_recent_pair_not_rematched_within_14_days(k):
    mid = two_way(k)
    assert k.act("An", mid, "decline").status_code == 200
    # Dũng–Hà vẫn đang hoạt động; An, Châu về hàng chờ nhưng đã ghép với nhau trong 14 ngày
    rnd = k.run_round()
    assert rnd["matches"] == [] and len(rnd["waitingStudentIds"]) == 2


def test_priority_node_is_c2_15(k):
    r = k.as_("gv").post(f"/api/v1/classes/{k.w.class_id}/matching-rounds", json={"priorityNodeId": str(k.node(N5))})
    assert r.status_code == 501


# --- Bật / tắt tham gia (FR-PM-01, BR-10) --------------------------------------------------------


def test_opt_in_toggle(k):
    r = k.as_("Khang").put(f"/api/v1/enrollments/{k.enrollment['Khang']}/peer-opt-in", json={"peerOptIn": True})
    assert r.status_code == 200 and r.json() == {"peerOptIn": True}
    k.db.expire_all()
    assert k.db.get(Enrollment, k.enrollment["Khang"]).peer_opt_in is True
    r = k.as_("An").put(f"/api/v1/enrollments/{k.enrollment['Khang']}/peer-opt-in", json={"peerOptIn": False})
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"
    r = k.as_("An").put(f"/api/v1/enrollments/{uuid4()}/peer-opt-in", json={"peerOptIn": False})
    assert r.status_code == 404 and r.json()["error"]["code"] == "ENROLLMENT_NOT_FOUND"


def test_opt_out_declines_pending_suggestions(k):
    mid = two_way(k)
    r = k.as_("An").put(f"/api/v1/enrollments/{k.enrollment['An']}/peer-opt-in", json={"peerOptIn": False})
    assert r.status_code == 200
    assert status(k, mid) == MatchStatus.DECLINED


# --- Phản hồi gợi ý (UC22) -----------------------------------------------------------------------


def test_accept_both_then_studied_both(k):
    mid = two_way(k)
    r = k.act("An", mid, "accept")
    assert r.status_code == 200 and r.json()["status"] == "WAITING_OTHER" and r.json()["acceptedByMe"] is True
    assert r.json()["partnerEmail"] is None, "chưa đủ hai bên chấp nhận thì chưa chia sẻ liên hệ"
    assert k.act("An", mid, "accept").json()["status"] == "WAITING_OTHER", "bấm lặp an toàn"
    r = k.act("Chau", mid, "accept")
    body = r.json()
    assert body["status"] == "ACCEPTED" and body["partnerName"] == "An" and body["partnerEmail"].startswith("an.")
    assert body["iTeach"] == [N4] and body["iLearn"] == [N5]

    r = k.act("An", mid, "decline")
    assert r.status_code == 409 and r.json()["error"]["code"] == "MATCH_INVALID_STATE"

    r = k.act("An", mid, "studied")
    assert r.json()["status"] == "ACCEPTED" and r.json()["studiedByMe"] is True
    r = k.act("Chau", mid, "studied")
    assert r.json()["status"] == "STUDIED"
    assert datetime.fromisoformat(r.json()["expiresAt"]) > datetime.now(UTC) + timedelta(days=6)


def test_studied_before_accept_rejected(k):
    mid = two_way(k)
    r = k.act("An", mid, "studied")
    assert r.status_code == 409 and r.json()["error"]["code"] == "MATCH_INVALID_STATE"
    assert r.json()["error"]["details"]["status"] == "PROPOSED"


def test_decline(k):
    mid = two_way(k)
    k.act("An", mid, "accept")
    r = k.act("Chau", mid, "decline")
    assert r.status_code == 200 and r.json()["status"] == "DECLINED"
    r = k.act("An", mid, "accept")
    assert r.status_code == 409


def test_non_member_cannot_respond(k):
    mid = two_way(k)
    r = k.act("Ha", mid, "accept")
    assert r.status_code == 403 and r.json()["error"]["code"] == "NOT_MATCH_MEMBER"
    r = k.act("Ha", str(uuid4()), "accept")
    assert r.status_code == 404 and r.json()["error"]["code"] == "MATCH_NOT_FOUND"


def test_list_matches_student_sees_own_lecturer_sees_all(k):
    k.run_round()
    r = k.as_("An").get(f"/api/v1/classes/{k.w.class_id}/matches")
    assert r.status_code == 200 and len(r.json()) == 1 and r.json()[0]["partnerName"] == "Chau"
    r = k.as_("Khang").get(f"/api/v1/classes/{k.w.class_id}/matches")
    assert r.status_code == 200 and r.json() == []
    r = k.as_("gv").get(f"/api/v1/classes/{k.w.class_id}/matches")
    assert r.status_code == 200 and len(r.json()) == 2
    k.w.current = k.w.sv_out
    r = k.w.api.get(f"/api/v1/classes/{k.w.class_id}/matches")
    assert r.status_code == 403 and r.json()["error"]["code"] == "NOT_ENROLLED"


# --- Hết hạn (BR-09, Xong khi 2) -----------------------------------------------------------------


def test_proposed_expires_after_48_hours(k):
    mid = two_way(k)
    k.act("An", mid, "accept")  # WAITING_OTHER cũng hết hạn
    svc = MatchingService(k.db)
    now = datetime.now(UTC)
    assert svc.expire_due(now + timedelta(hours=47))["EXPIRED"] == 0
    assert status(k, mid) == MatchStatus.WAITING_OTHER
    assert svc.expire_due(now + timedelta(hours=49))["EXPIRED"] == 2  # cả cặp Dũng–Hà
    assert status(k, mid) == MatchStatus.EXPIRED


def test_beat_task_expires_overdue(k, monkeypatch):
    import app.workers.matching as worker

    mid = two_way(k)
    m = k.db.get(PeerMatch, UUID(mid))
    m.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    k.db.flush()

    monkeypatch.setattr(worker, "SessionLocal", lambda: _NoClose(k.db))
    result = worker.expire_matches()
    assert result["EXPIRED"] == 1
    assert status(k, mid) == MatchStatus.EXPIRED


def test_accept_after_deadline_is_expired(k):
    mid = two_way(k)
    m = k.db.get(PeerMatch, UUID(mid))
    m.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    k.db.flush()
    r = k.act("An", mid, "accept")
    assert r.status_code == 409 and r.json()["error"]["code"] == "MATCH_EXPIRED"
    assert status(k, mid) == MatchStatus.EXPIRED


def test_scheduled_round_picks_class_with_opt_ins(k):
    assert k.w.class_id in MatchingService(k.db).scheduled_class_ids()


def test_scheduled_round_skips_class_without_published_tree(world):
    for sid in (world.sv, world.sv_out):
        enrollment = world.db.scalar(
            select(Enrollment).where(Enrollment.class_id == world.class_id, Enrollment.student_id == sid)
        )
        if enrollment is None:
            world.db.add(Enrollment(class_id=world.class_id, student_id=sid, peer_opt_in=True))
        else:
            enrollment.peer_opt_in = True
    world.db.flush()
    assert world.class_id not in MatchingService(world.db).scheduled_class_ids()


def test_matching_priority_uses_all_enrolled_students_including_opted_out(k):
    snapshot = MasteryService(k.db).matching_snapshot(k.w.class_id)
    # 6 SV ghi danh: 5 người trong PLAN và SV mặc định của World. Chỉ 4 người bật ghép cặp.
    assert snapshot.pass_rate[N5] == pytest.approx(2 / 6)
    assert snapshot.pass_rate[N4] == pytest.approx(2 / 6)
    assert snapshot.pass_rate[N2] == pytest.approx(3 / 6)


# --- Xác nhận lại (UC23, Xong khi 3) -------------------------------------------------------------


def _followup(k: Klass, learner: str, it: PeerMatchItem, verdict=Verdict.PASSED, with_item=True) -> SessionResult:
    return SessionResult(
        session_id=uuid4(),
        student_id=k.ids[learner],
        node_id=it.node_id,
        class_id=k.w.class_id,
        state=MasteryState.MASTERED if verdict == Verdict.PASSED else MasteryState.NOT_PASSED,
        verdict=verdict,
        total_score=85 if verdict == Verdict.PASSED else 40,
        criteria=[],
        is_peer_followup=True,
        peer_match_item_id=it.id if with_item else None,
    )


def test_reverify_passed_marks_match_verified(k):
    register_matching(k.bus, session_factory=lambda: _NoClose(k.db))
    mid = to_studied(k)
    it_chau, it_an = item(k, mid, "Chau"), item(k, mid, "An")

    k.bus.publish(TOPIC_SESSION_COMPLETED, _followup(k, "Chau", it_chau, Verdict.FAILED))
    k.db.expire_all()
    assert item(k, mid, "Chau").verified is False, "Chưa đạt ⇒ giữ chưa xác nhận (5a)"

    k.bus.publish(TOPIC_SESSION_COMPLETED, _followup(k, "Chau", it_chau))
    k.db.expire_all()
    assert item(k, mid, "Chau").verified is True and item(k, mid, "Chau").verified_at is not None
    assert status(k, mid) == MatchStatus.STUDIED, "còn mục của An"

    # sự kiện không kèm peerMatchItemId (nguồn cũ) vẫn khớp theo người học + nút
    k.bus.publish(TOPIC_SESSION_COMPLETED, _followup(k, "An", it_an, with_item=False))
    assert status(k, mid) == MatchStatus.VERIFIED


def test_reverify_ignores_wrong_learner(k):
    mid = to_studied(k)
    it = item(k, mid, "Chau")
    assert MatchingService(k.db).verify_from_session(_followup(k, "An", it)) is False
    k.db.expire_all()
    assert item(k, mid, "Chau").verified is False


def test_reverify_ignores_same_node_key_from_another_class(k):
    mid = to_studied(k)
    it = item(k, mid, "Chau")
    course_id = k.db.get(ClassSection, k.w.class_id).course_id
    api = k.as_("gv")
    created = api.post("/api/v1/classes", json={"courseId": str(course_id), "name": "Lớp khác", "semester": "HK1"})
    assert created.status_code == 201, created.text
    other_class_id = UUID(created.json()["id"])
    k.db.add(Enrollment(class_id=other_class_id, student_id=k.ids["Chau"]))
    k.db.flush()
    imported = api.post(f"/api/v1/classes/{other_class_id}/tree-versions", json=_c209.SEED)
    assert imported.status_code == 201, imported.text
    other_tree = imported.json()
    _approve_all(k.w, other_tree)
    published = api.post(f"/api/v1/tree-versions/{other_tree['id']}/publish")
    assert published.status_code == 200, published.text
    other_node_id = UUID(next(n["id"] for n in published.json()["nodes"] if n["key"] == N5))
    # Key nút giống nhau giữa các lớp không chứng minh đã học nút của lớp đang ghép cặp.
    result = _followup(k, "Chau", it).model_copy(update={"class_id": other_class_id, "node_id": other_node_id})
    assert MatchingService(k.db).verify_from_session(result) is False
    k.db.expire_all()
    assert item(k, mid, "Chau").verified is False


def test_reverify_after_seven_day_deadline_does_not_verify_item(k):
    mid = to_studied(k)
    it = item(k, mid, "Chau")
    deadline = k.db.get(PeerMatch, UUID(mid)).expires_at
    late = deadline + timedelta(seconds=1)
    result = _followup(k, "Chau", it).model_copy(update={"completed_at": late})
    assert MatchingService(k.db, now=lambda: late).verify_from_session(result) is False
    k.db.expire_all()
    assert item(k, mid, "Chau").verified is False


def test_reverify_ignores_wrong_node_even_with_matching_item_id(k):
    mid = to_studied(k)
    it = item(k, mid, "Chau")
    result = _followup(k, "Chau", it).model_copy(update={"node_id": k.node(N2)})
    assert MatchingService(k.db).verify_from_session(result) is False
    k.db.expire_all()
    assert item(k, mid, "Chau").verified is False


def test_reverify_requires_studied_match(k):
    mid = two_way(k)
    it = item(k, mid, "Chau")
    assert MatchingService(k.db).verify_from_session(_followup(k, "Chau", it)) is False
    k.db.expire_all()
    assert item(k, mid, "Chau").verified is False


def test_start_followup_rejects_another_students_item(k):
    mid = to_studied(k)
    it = item(k, mid, "Chau")
    # Hà có thể mở phiên thường ở N5, nhưng không được gắn mục xác nhận lại của Châu.
    r = k.as_("Ha").post(
        "/api/v1/sessions", json={"nodeId": str(it.node_id), "inputMode": "TEXT", "peerMatchItemId": str(it.id)}
    )
    assert r.status_code == 403, r.text
    assert k.db.scalar(select(TeachingSession.id).where(TeachingSession.peer_match_item_id == it.id)) is None


def test_start_followup_rejects_wrong_node(k):
    k.run_round()
    own_matches = k.as_("Ha").get(f"/api/v1/classes/{k.w.class_id}/matches")
    assert own_matches.status_code == 200, own_matches.text
    mid = own_matches.json()[0]["id"]
    for action in ("accept", "studied"):
        for name in ("Ha", "Dung"):
            assert k.act(name, mid, action).status_code == 200
    it = item(k, mid, "Ha")
    # N2 và nút của mục ghép cặp đều đang mở cho Hà, nhưng chỉ nút của mục mới là phiên xác nhận lại.
    assert it.node_id != k.node(N2)
    r = k.as_("Ha").post(
        "/api/v1/sessions", json={"nodeId": str(k.node(N2)), "inputMode": "TEXT", "peerMatchItemId": str(it.id)}
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "PEER_ITEM_NODE_MISMATCH"
    assert k.db.scalar(select(TeachingSession.id).where(TeachingSession.peer_match_item_id == it.id)) is None


def test_studied_expiry_partial_or_unverified(k):
    mid = to_studied(k)
    svc = MatchingService(k.db)
    assert svc.verify_from_session(_followup(k, "Chau", item(k, mid, "Chau"))) is True
    later = datetime.now(UTC) + timedelta(days=8)
    counts = svc.expire_due(later)
    assert counts["PARTIALLY_VERIFIED"] == 1 and status(k, mid) == MatchStatus.PARTIALLY_VERIFIED
    # cặp Dũng–Hà vẫn PROPOSED ⇒ hết hạn 48 giờ
    assert counts["EXPIRED"] == 1


def test_full_followup_session_carries_peer_match_item(k):
    """Luồng thật qua Orchestrator (C1-07): POST /sessions có peerMatchItemId ⇒ session.completed mang id đó."""
    got: list[SessionResult] = []
    k.bus.subscribe(TOPIC_SESSION_COMPLETED, got.append)
    k.bus.subscribe(TOPIC_SESSION_COMPLETED, lambda e: MasteryService(k.db, bus=k.bus).apply_result(e))
    register_matching(k.bus, session_factory=lambda: _NoClose(k.db))
    mid = to_studied(k)
    it = item(k, mid, "Chau")  # Châu học N5 từ An
    api = k.as_("Chau")
    r = api.post(
        "/api/v1/sessions", json={"nodeId": str(it.node_id), "inputMode": "TEXT", "peerMatchItemId": str(it.id)}
    )
    assert r.status_code == 201, r.text
    sid = r.json()["sessionId"]
    reply = api.post(f"/api/v1/sessions/{sid}/turns", json={"turnType": "EXPLANATION", "text": "Con trỏ lưu địa chỉ."})
    reply = reply.json()
    for _ in range(10):
        if reply["question"] is None:
            break
        reply = api.post(f"/api/v1/sessions/{sid}/turns", json={"turnType": "ANSWER", "text": "Trả lời."}).json()
    assert reply["status"] == "COMPLETED"
    assert len(got) == 1 and got[0].peer_match_item_id == it.id and got[0].is_peer_followup is True
    k.db.expire_all()
    assert item(k, mid, "Chau").verified is (got[0].verdict == Verdict.PASSED)
