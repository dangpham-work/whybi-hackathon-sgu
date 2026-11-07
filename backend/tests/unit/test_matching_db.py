"""C2-14 – Xong khi: Ví dụ 6.6.4 ra đúng cặp; gợi ý quá 48 giờ tự hết hạn; xác nhận lại Đạt thì cặp "đã xác nhận".

Cần Postgres đã migrate (TEST_DATABASE_URL). Dùng lại World / cây mẫu của C2-09 và MasteryService (C2-10).
Ma trận dựng trên cây mẫu theo tinh thần Hình 6.11 (mọi SV đã Đạt N1, N3 nên N2, N4, N5 là Biên):
  An Đạt N2, N5 · Châu Đạt N2, N4 · Hà chưa Đạt thêm · Dũng Đạt N2, N4, N5 · Khang chỉ Đạt N1 và TẮT ghép cặp.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, update

from app.models.enums import MasteryState, MatchStatus, Role, Verdict
from app.models.peer import NodeReviewWindow, PeerMatch, PeerMatchItem
from app.models.schemas.mastery import TOPIC_SESSION_COMPLETED
from app.models.schemas.session import SessionResult
from app.models.session import MasteryRecord, TeachingSession
from app.models.users import ClassSection, Enrollment, Student, User
from app.realtime.bus import InMemoryEventBus
from app.services.live_matching import LiveMatching
from app.services.live_matching import register_handlers as register_live
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
        self.svc = MasteryService(w.db, bus=bus)
        for name, (keys, opt_in) in PLAN.items():
            self.add_student(name, keys, opt_in)

    def add_student(self, name: str, keys: list[str], opt_in: bool) -> None:
        """Thêm SV vào lớp, đã Đạt các nút `keys` (theo thứ tự)."""
        w = self.w
        u = User(id=uuid4(), full_name=name, email=f"{name.lower()}.{uuid4().hex[:6]}@whybi.test", password_hash="x")
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
        self.svc.ensure_student(w.class_id, u.id)
        for k in keys:
            self.attempt(name, k, passed=True)
        self.name_of = {v: k for k, v in self.ids.items()}

    def attempt(self, name: str, key: str, passed: bool = True) -> None:
        """Một phiên của SV ở nút `key`: Đạt ⇒ MASTERED, không ⇒ NOT_PASSED (phát mastery.changed qua bus)."""
        w, uid, sid = self.w, self.ids[name], uuid4()
        w.db.add(
            TeachingSession(
                id=sid, student_id=uid, node_id=self.node(key), class_id=w.class_id, input_mode="TEXT", status="CREATED"
            )
        )
        w.db.flush()
        self.svc.start_session(uid, self.node(key), sid)
        self.svc.apply_result(
            SessionResult(
                session_id=sid,
                student_id=uid,
                node_id=self.node(key),
                class_id=w.class_id,
                state=MasteryState.MASTERED if passed else MasteryState.NOT_PASSED,
                verdict=Verdict.PASSED if passed else Verdict.FAILED,
                total_score=90 if passed else 40,
                criteria=[],
            )
        )

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


def test_priority_node_unknown_node_404_and_known_node_runs(k):
    url = f"/api/v1/classes/{k.w.class_id}/matching-rounds"
    r = k.as_("gv").post(url, json={"priorityNodeId": str(uuid4())})
    assert r.status_code == 404 and r.json()["error"]["code"] == "NODE_NOT_IN_TREE"
    r = k.as_("gv").post(url, json={"priorityNodeId": str(k.node(N5))})
    assert r.status_code == 201, r.text
    body = r.json()
    assert len(body["matches"]) == 2
    assert N5 in {i["nodeKey"] for m in body["matches"] for i in m["items"]}, "cặp có người dạy N5 được chọn"


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


# --- Ghép theo sự kiện trong hạn kiểm tra bài cũ của nút (C2-15) ------------------------------------
# Người Đạt dạy tối đa 3 người chưa Đạt; không đạt ⇒ ghép ngay với người dạy còn chỗ, chưa có ⇒ chờ.


def _window(k, node: str, hours: float = 24, who: str = "gv"):
    when = (datetime.now(UTC) + timedelta(hours=hours)).isoformat()
    url = f"/api/v1/classes/{k.w.class_id}/nodes/{k.node(node)}/review-window"
    return k.as_(who).put(url, json={"deadlineAt": when})


@pytest.fixture
def live(k, bus):
    """Nghe mastery.changed như tiến trình mastery_listener."""
    register_live(bus, session_factory=lambda: _NoClose(k.db))
    return k


def _opt(k, name: str, on: bool) -> None:
    r = k.as_(name).put(f"/api/v1/enrollments/{k.enrollment[name]}/peer-opt-in", json={"peerOptIn": on})
    assert r.status_code == 200, r.text


def _live_matches(k, node: str) -> list[tuple[str, str, str]]:
    """(người dạy, người học, trạng thái) của mọi cặp có mục ở nút `node`."""
    k.db.expire_all()
    rows = k.db.execute(
        select(PeerMatch)
        .join(PeerMatchItem, PeerMatchItem.match_id == PeerMatch.id)
        .where(PeerMatchItem.node_id == k.node(node))
        .order_by(PeerMatch.created_at)
    ).scalars()
    return [(k.name_of[m.student_a_id], k.name_of[m.student_b_id], m.status) for m in rows]


def test_live_failer_is_paired_at_once_with_a_passer(live):
    k = live
    assert _window(k, N2).status_code == 200
    k.attempt("Ha", N2, passed=False)
    [(teacher, learner, st)] = _live_matches(k, N2)
    assert teacher in {"An", "Chau", "Dung"} and learner == "Ha" and st == "PROPOSED"
    [m] = k.as_("gv").get(f"/api/v1/classes/{k.w.class_id}/matches").json()
    assert m["oneWay"] is True and [i["nodeKey"] for i in m["items"]] == [N2]


def test_live_failer_waits_for_a_passer_then_is_paired_when_one_arrives(live):
    k = live
    for name in ("Chau", "Dung"):  # hai người Đạt N4 tắt ghép cặp ⇒ chưa có người dạy
        _opt(k, name, False)
    _window(k, N4)
    k.attempt("An", N4, passed=False)
    assert _live_matches(k, N4) == []
    k.attempt("Ha", N4, passed=True)  # Hà vừa Đạt N4 ⇒ nhận kèm An ngay
    assert _live_matches(k, N4) == [("Ha", "An", "PROPOSED")]


def test_live_teacher_takes_at_most_three_learners(live):
    k = live
    _opt(k, "Chau", False)  # Dũng là người dạy N4 duy nhất
    for name in ("L1", "L2", "L3", "L4"):
        k.add_student(name, [N1, N3], True)
    _window(k, N4)
    for name in ("L1", "L2", "L3", "L4"):
        k.attempt(name, N4, passed=False)
    got = _live_matches(k, N4)
    assert sorted(learner for _, learner, _ in got) == ["L1", "L2", "L3"], "đến trước được trước, bạn thứ 4 chờ"
    assert {teacher for teacher, _, _ in got} == {"Dung"}
    _opt(k, "Chau", True)
    LiveMatching(k.db).rebalance_class(k.w.class_id)  # beat dự phòng: có người dạy mới thì bạn chờ được ghép
    assert ("Chau", "L4", "PROPOSED") in _live_matches(k, N4)


def test_live_load_is_spread_across_passers(live):
    k = live
    _window(k, N4)  # Châu và Dũng cùng Đạt N4
    k.attempt("An", N4, passed=False)
    k.attempt("Ha", N4, passed=False)
    assert {teacher for teacher, _, _ in _live_matches(k, N4)} == {"Chau", "Dung"}


def test_live_stops_after_the_deadline(live):
    k = live
    assert _window(k, N2).status_code == 200
    k.db.execute(
        update(NodeReviewWindow)
        .where(NodeReviewWindow.class_id == k.w.class_id)
        .values(deadline_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    k.db.flush()
    k.attempt("Ha", N2, passed=False)
    assert _live_matches(k, N2) == []


def test_live_without_a_window_does_nothing(live):
    live.attempt("Ha", N2, passed=False)
    assert _live_matches(live, N2) == []


def test_live_ignores_students_who_opted_out(live):
    k = live
    _opt(k, "Ha", False)
    _window(k, N2)
    k.attempt("Ha", N2, passed=False)
    assert _live_matches(k, N2) == []


def _retry_now(k, name: str, node: str) -> None:
    """Bỏ thời gian chờ thử lại (BR-11) để test cho SV làm lại ngay."""
    k.db.execute(
        update(MasteryRecord)
        .where(MasteryRecord.student_id == k.ids[name], MasteryRecord.node_id == k.node(node))
        .values(last_failed_at=datetime.now(UTC) - timedelta(hours=1))
    )
    k.db.flush()


def test_live_pending_match_is_dropped_when_the_learner_passes_later(live):
    k = live
    _window(k, N2)
    k.attempt("Ha", N2, passed=False)
    _retry_now(k, "Ha", N2)
    k.attempt("Ha", N2, passed=True)
    [(teacher, learner, st)] = _live_matches(k, N2)
    assert learner == "Ha" and st == "DECLINED", "Hà đã Đạt nên không cần người dạy nữa"


def test_live_declined_pair_is_not_repeated(live):
    k = live
    _window(k, N2)
    k.attempt("Ha", N2, passed=False)
    k.db.expire_all()
    m = k.db.scalar(select(PeerMatch).join(PeerMatchItem).where(PeerMatchItem.node_id == k.node(N2)))
    first_teacher = k.name_of[m.student_a_id]
    assert k.act("Ha", str(m.id), "decline").status_code == 200
    LiveMatching(k.db).rebalance_class(k.w.class_id)
    again = [t for t, _, st in _live_matches(k, N2) if st == "PROPOSED"]
    assert len(again) == 1 and again[0] != first_teacher, "không ghép lại đúng người vừa từ chối"


def test_review_window_api_permissions_and_validation(k):
    r = _window(k, N2, who="gv_other")
    assert r.status_code == 403 and r.json()["error"]["code"] == "NOT_CLASS_OWNER"
    r = _window(k, N2, who="An")
    assert r.status_code == 403
    r = _window(k, N2, hours=-1)
    assert r.status_code == 422 and r.json()["error"]["code"] == "DEADLINE_IN_PAST"
    url = f"/api/v1/classes/{k.w.class_id}/nodes/{uuid4()}/review-window"
    r = k.as_("gv").put(url, json={"deadlineAt": (datetime.now(UTC) + timedelta(hours=1)).isoformat()})
    assert r.status_code == 404 and r.json()["error"]["code"] == "NODE_NOT_IN_TREE"


def test_review_window_can_be_moved_and_is_one_per_node(k):
    first = _window(k, N2, hours=2).json()
    second = _window(k, N2, hours=5).json()
    assert first["nodeKey"] == second["nodeKey"] == N2 and first["deadlineAt"] < second["deadlineAt"]
    rows = k.as_("gv").get(f"/api/v1/classes/{k.w.class_id}/review-windows").json()
    assert len(rows) == 1 and rows[0]["open"] is True


def test_review_windows_report_students_still_waiting(live):
    k = live
    for name in ("Chau", "Dung"):
        _opt(k, name, False)
    _window(k, N4)
    k.attempt("An", N4, passed=False)
    [w] = k.as_("gv").get(f"/api/v1/classes/{k.w.class_id}/review-windows").json()
    assert w["nodeKey"] == N4 and w["teacherCount"] == 0 and w["matchedCount"] == 0
    assert w["waitingStudentIds"] == [str(k.ids["An"])]
    assert "giảng trực tiếp" in w["message"]


def test_daily_batch_skips_classes_with_an_open_review_window(k):
    assert k.w.class_id in MatchingService(k.db).scheduled_class_ids()
    assert _window(k, N2).status_code == 200
    assert k.w.class_id not in MatchingService(k.db).scheduled_class_ids()


# --- GV điều chỉnh cặp, thống kê hiệu quả (C2-15 phần 2) -------------------------------------------


def adjust(k: Klass, who: str, mid: str, body: dict):
    return k.as_(who).patch(f"/api/v1/matches/{mid}", json=body)


def test_gv_cancel_pair_then_cannot_act_again(k):
    mid = two_way(k)
    r = adjust(k, "gv", mid, {"cancel": True})
    assert r.status_code == 200 and r.json()["status"] == "DECLINED"
    r = adjust(k, "gv", mid, {"cancel": True})
    assert r.status_code == 409 and r.json()["error"]["code"] == "MATCH_INVALID_STATE"


def test_adjust_permissions_and_bad_body(k):
    mid = two_way(k)
    assert adjust(k, "An", mid, {"cancel": True}).status_code == 403
    k.w.current = k.w.gv_other
    r = k.w.api.patch(f"/api/v1/matches/{mid}", json={"cancel": True})
    assert r.status_code == 403 and r.json()["error"]["code"] == "NOT_CLASS_OWNER"
    assert adjust(k, "gv", mid, {}).status_code == 422
    assert adjust(k, "gv", mid, {"cancel": True, "replaceStudentId": str(k.ids["Ha"])}).status_code == 422
    assert adjust(k, "gv", mid, {"replaceStudentId": str(k.ids["Chau"])}).status_code == 422
    assert adjust(k, "gv", str(uuid4()), {"cancel": True}).json()["error"]["code"] == "MATCH_NOT_FOUND"


def test_gv_replaces_student_recomputes_items_and_resets_acceptance(k):
    mid = two_way(k)
    assert k.act("An", mid, "accept").status_code == 200
    k.add_student("Binh", [N1, N3, N2, N4], True)  # cùng năng lực với Châu, chưa trong cặp nào
    r = adjust(k, "gv", mid, {"replaceStudentId": str(k.ids["Chau"]), "withStudentId": str(k.ids["Binh"])})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "PROPOSED"
    assert {body["studentAId"], body["studentBId"]} == {str(k.ids["An"]), str(k.ids["Binh"])}
    teach = {(k.name_of[UUID(i["teacherId"])], i["nodeKey"]) for i in body["items"]}
    assert teach == {("An", N5), ("Binh", N4)}
    k.db.expire_all()
    m = k.db.get(PeerMatch, UUID(mid))
    assert not (m.accepted_by_a or m.accepted_by_b), "đổi người ⇒ hai bên phải chấp nhận lại"
    assert k.act("Chau", mid, "accept").status_code == 403, "Châu đã ra khỏi cặp"
    assert k.act("Binh", mid, "accept").status_code == 200


def test_replace_validations(k):
    mid = two_way(k)
    a, c = str(k.ids["An"]), str(k.ids["Chau"])
    err = lambda body: adjust(k, "gv", mid, body).json()["error"]["code"]  # noqa: E731
    assert err({"replaceStudentId": str(k.ids["Ha"]), "withStudentId": str(k.ids["Khang"])}) == "REPLACE_NOT_IN_MATCH"
    assert err({"replaceStudentId": c, "withStudentId": a}) == "REPLACE_NOT_IN_MATCH"
    assert err({"replaceStudentId": c, "withStudentId": str(uuid4())}) == "STUDENT_NOT_IN_CLASS"
    assert err({"replaceStudentId": c, "withStudentId": str(k.ids["Khang"])}) == "STUDENT_NOT_OPTED_IN"
    assert err({"replaceStudentId": c, "withStudentId": str(k.ids["Ha"])}) == "STUDENT_BUSY"
    k.add_student("Zed", [N1, N3, N2, N5], True)  # giống hệt An: không ai có gì để dạy người kia
    assert err({"replaceStudentId": c, "withStudentId": str(k.ids["Zed"])}) == "NO_COMPLEMENTARY_NODES"
    assert status(k, mid) == MatchStatus.PROPOSED, "lỗi thì cặp giữ nguyên"


def test_matching_stats_rates(k):
    url = f"/api/v1/classes/{k.w.class_id}/matching-stats"
    zero = k.as_("gv").get(url).json()
    assert zero["totalMatches"] == 0 and zero["acceptRate"] == 0 and zero["verifiedRate"] == 0
    mid = to_studied(k)  # cũng tạo cặp Dũng–Hà (một chiều), chưa ai phản hồi
    s = k.as_("gv").get(url).json()
    assert (s["totalMatches"], s["accepted"], s["studied"]) == (2, 1, 1)
    assert s["acceptRate"] == 0.5 and s["studiedRate"] == 1.0
    assert s["itemsTotal"] == 2 and s["itemsVerified"] == 0 and s["verifiedRate"] == 0
    k.db.expire_all()
    it = item(k, mid, "Chau")
    it.verified = True
    k.db.commit()
    s = k.as_("gv").get(url).json()
    assert s["itemsVerified"] == 1 and s["verifiedRate"] == 0.5


def test_matching_stats_permissions(k):
    url = f"/api/v1/classes/{k.w.class_id}/matching-stats"
    assert k.as_("An").get(url).status_code == 403
    k.w.current = k.w.gv_other
    r = k.w.api.get(url)
    assert r.status_code == 403 and r.json()["error"]["code"] == "NOT_CLASS_OWNER"
