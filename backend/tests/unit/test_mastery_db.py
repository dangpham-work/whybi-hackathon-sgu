"""C2-10 – Xong khi: kết quả Đạt mở khóa nút kế tiếp; phát hành phiên bản mới vẫn giữ trạng thái cũ.

Cần Postgres đã migrate (TEST_DATABASE_URL). Dùng lại World / cây mẫu của test_tree_edit_db (C2-09).
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier, Event
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.enums import MasteryChangeReason, MasteryState, Verdict
from app.models.schemas.mastery import TOPIC_MASTERY_CHANGED, TOPIC_SESSION_COMPLETED, MasteryChanged
from app.models.schemas.session import SessionResult
from app.models.session import MasteryRecord, TeachingSession
from app.realtime.bus import InMemoryEventBus
from app.services.mastery import MasteryService, register_handlers
from app.services.skill_tree import SkillTreeService
from tests.unit import test_tree_concurrency_db as _concurrent
from tests.unit import test_tree_edit_db as _c209
from tests.unit.test_tree_concurrency_db import draft
from tests.unit.test_tree_edit_db import DB_URL, _approve_all, _import_seed

world = _c209.world  # fixture World + transaction rollback của C2-09
committed_world = _concurrent.committed_world

pytestmark = pytest.mark.skipif(not DB_URL, reason="đặt TEST_DATABASE_URL để chạy trên Postgres thật")

S = MasteryState


@pytest.fixture
def bus():
    return InMemoryEventBus()


@pytest.fixture
def events(bus) -> list[MasteryChanged]:
    got: list[MasteryChanged] = []
    bus.subscribe(TOPIC_MASTERY_CHANGED, got.append)
    return got


@pytest.fixture
def published(world, bus, events, monkeypatch):
    """Lớp có cây mẫu đã phát hành (v1). Trả (world, tree_json, MasteryService).
    Phụ thuộc `events` để bắt cả sự kiện khởi tạo lúc phát hành."""
    import app.services.mastery as mastery_mod

    monkeypatch.setattr(mastery_mod, "get_bus", lambda: bus)
    tv = _import_seed(world)
    _approve_all(world, tv)
    r = world.api.post(f"/api/v1/tree-versions/{tv['id']}/publish")
    assert r.status_code == 200, r.text
    return world, r.json(), MasteryService(world.db, bus=bus)


def node_id(tree: dict, key: str):
    from uuid import UUID

    return UUID(next(n["id"] for n in tree["nodes"] if n["key"] == key))


def states(svc: MasteryService, w, tree) -> dict[str, MasteryState]:
    m = svc.my_map(w.class_id, w.sv)
    return {p.node_key: p.state for p in m.progress}


def new_session(w, tree, key: str):
    s = TeachingSession(
        id=uuid4(),
        student_id=w.sv,
        node_id=node_id(tree, key),
        class_id=w.class_id,
        input_mode="TEXT",
        status="CREATED",
    )
    w.db.add(s)
    w.db.flush()
    return s.id


def result(w, tree, key, sid, verdict: Verdict, score: float) -> SessionResult:
    return SessionResult(
        session_id=sid,
        student_id=w.sv,
        node_id=node_id(tree, key),
        class_id=w.class_id,
        state=S.MASTERED if verdict == Verdict.PASSED else S.NOT_PASSED,
        verdict=verdict,
        total_score=score,
        criteria=[],
    )


def pass_node(svc, w, tree, key, score=80.0):
    sid = new_session(w, tree, key)
    svc.start_session(w.sv, node_id(tree, key), sid)
    return svc.apply_result(result(w, tree, key, sid, Verdict.PASSED, score))


# --- Khởi tạo khi phát hành (Bảng 4.8 dòng 1–2) --------------------------------------------------


def test_publish_initialises_roots_available_rest_locked(published, events):
    w, tree, svc = published
    st = states(svc, w, tree)
    assert st["n1_bien_bo_nho"] == S.AVAILABLE
    assert {k for k, v in st.items() if v == S.LOCKED} == {n["key"] for n in tree["nodes"]} - {"n1_bien_bo_nho"}
    init = [e for e in events if e.reason == MasteryChangeReason.PUBLISH_INIT]
    assert len(init) == 11 and all(e.old_state is None and e.student_id == w.sv for e in init)


def test_my_map_api_contract(published):
    w, tree, _ = published
    w.current = w.sv
    r = w.api.get(f"/api/v1/classes/{w.class_id}/my-map")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tree"]["versionNo"] == 1 and body["totalCount"] == 11 and body["masteredCount"] == 0
    assert body["frontier"] == ["n1_bien_bo_nho"]
    n5 = next(p for p in body["progress"] if p["nodeKey"] == "n5_con_tro")
    assert n5["state"] == "LOCKED" and set(n5["missingPrerequisites"]) == {"n1_bien_bo_nho", "n3_ham_tham_so"}
    assert n5["canStart"] is False
    n1 = next(p for p in body["progress"] if p["nodeKey"] == "n1_bien_bo_nho")
    assert n1["canStart"] is True and n1["attempts"] == 0 and n1["bestScore"] is None


def test_my_map_errors(published):
    w, _, _ = published
    w.current = w.sv_out
    r = w.api.get(f"/api/v1/classes/{w.class_id}/my-map")
    assert r.status_code == 403 and r.json()["error"]["code"] == "NOT_ENROLLED"


def test_my_map_before_publish_is_404(world):
    world.current = world.sv
    r = world.api.get(f"/api/v1/classes/{world.class_id}/my-map")
    assert r.status_code == 404 and r.json()["error"]["code"] == "TREE_NOT_PUBLISHED"


def test_student_joining_after_publish_gets_initialised(published):
    from app.models.users import Enrollment

    w, tree, svc = published
    w.db.add(Enrollment(class_id=w.class_id, student_id=w.sv_out))
    w.db.flush()
    m = svc.my_map(w.class_id, w.sv_out)
    assert {p.node_key: p.state for p in m.progress}["n1_bien_bo_nho"] == S.AVAILABLE


# --- Đạt mở khóa (Xong khi 1, BR-02) -------------------------------------------------------------


def test_pass_unlocks_next_nodes(published, events):
    w, tree, svc = published
    ev = pass_node(svc, w, tree, "n1_bien_bo_nho", 82.5)
    st = states(svc, w, tree)
    assert st["n1_bien_bo_nho"] == S.MASTERED
    assert st["n2_mang"] == st["n3_ham_tham_so"] == S.AVAILABLE
    assert st["n5_con_tro"] == S.LOCKED, "N5 còn chờ N3"
    assert ev.reason == MasteryChangeReason.SESSION_PASSED and ev.new_state == S.MASTERED
    assert set(ev.unlocked_node_ids) == {node_id(tree, "n2_mang"), node_id(tree, "n3_ham_tham_so")}
    assert {e.node_key for e in events if e.reason == MasteryChangeReason.UNLOCKED} == {"n2_mang", "n3_ham_tham_so"}
    # N5 mở khi cả N1 và N3 đều Đạt
    pass_node(svc, w, tree, "n3_ham_tham_so")
    assert states(svc, w, tree)["n5_con_tro"] == S.AVAILABLE
    p1 = next(p for p in svc.my_map(w.class_id, w.sv).progress if p.node_key == "n1_bien_bo_nho")
    assert p1.best_score == 82.5 and p1.attempts == 1


def test_session_completed_event_drives_mastery(published, bus, events):
    """Luồng thật: Đăng phát session.completed → handler của MasteryService → mastery.changed."""
    w, tree, svc = published
    register_handlers(bus, session_factory=lambda: w.db)
    sid = new_session(w, tree, "n1_bien_bo_nho")
    svc.start_session(w.sv, node_id(tree, "n1_bien_bo_nho"), sid)
    bus.publish(TOPIC_SESSION_COMPLETED, result(w, tree, "n1_bien_bo_nho", sid, Verdict.PASSED, 90))
    assert any(e.reason == MasteryChangeReason.SESSION_PASSED and e.session_id == sid for e in events)
    assert states(svc, w, tree)["n2_mang"] == S.AVAILABLE


def test_same_result_twice_is_idempotent(published):
    w, tree, svc = published
    sid = new_session(w, tree, "n1_bien_bo_nho")
    svc.start_session(w.sv, node_id(tree, "n1_bien_bo_nho"), sid)
    r = result(w, tree, "n1_bien_bo_nho", sid, Verdict.PASSED, 80)
    assert svc.apply_result(r) is not None
    assert svc.apply_result(r) is None
    p1 = next(p for p in svc.my_map(w.class_id, w.sv).progress if p.node_key == "n1_bien_bo_nho")
    assert p1.attempts == 1


def test_result_for_locked_node_is_ignored(published, events):
    """Kết quả cho nút còn Khóa (không qua start_session) không được mở khóa trái BR-02."""
    w, tree, svc = published
    sid = new_session(w, tree, "n5_con_tro")
    n = len(events)
    assert svc.apply_result(result(w, tree, "n5_con_tro", sid, Verdict.PASSED, 95)) is None
    assert states(svc, w, tree)["n5_con_tro"] == S.LOCKED and len(events) == n


# --- Bắt đầu phiên, trượt, thời gian chờ (Bảng 4.8, BR-11) ---------------------------------------


def test_start_locked_node_rejected_with_missing_prerequisites(published):
    w, tree, svc = published
    with pytest.raises(AppError) as exc:
        svc.start_session(w.sv, node_id(tree, "n5_con_tro"), uuid4())
    assert exc.value.code == "NODE_LOCKED"
    assert set(exc.value.details["missingPrerequisites"]) == {"n1_bien_bo_nho", "n3_ham_tham_so"}
    check = svc.can_start(w.sv, node_id(tree, "n5_con_tro"))
    assert check.allowed is False and check.code == "NODE_LOCKED"


def test_fail_then_cooldown_then_retry(published):
    w, tree, svc = published
    n1 = node_id(tree, "n1_bien_bo_nho")
    sid = new_session(w, tree, "n1_bien_bo_nho")
    svc.start_session(w.sv, n1, sid)
    ev = svc.apply_result(result(w, tree, "n1_bien_bo_nho", sid, Verdict.FAILED, 40))
    assert ev.new_state == S.NOT_PASSED and ev.reason == MasteryChangeReason.SESSION_FAILED
    p = next(p for p in svc.my_map(w.class_id, w.sv).progress if p.node_key == "n1_bien_bo_nho")
    assert p.attempts == 1 and p.retry_at is not None and p.can_start is False
    with pytest.raises(AppError) as exc:
        svc.start_session(w.sv, n1, uuid4())
    assert exc.value.code == "RETRY_COOLDOWN"
    # 10 phút sau thì thử lại được
    rec = w.db.query(MasteryRecord).filter_by(student_id=w.sv, node_id=n1).one()
    rec.last_failed_at = datetime.now(UTC) - timedelta(minutes=11)
    w.db.flush()
    sid2 = new_session(w, tree, "n1_bien_bo_nho")
    assert svc.start_session(w.sv, n1, sid2).state == S.IN_PROGRESS


def test_start_twice_and_mastered_rejected(published):
    w, tree, svc = published
    n1 = node_id(tree, "n1_bien_bo_nho")
    sid = new_session(w, tree, "n1_bien_bo_nho")
    svc.start_session(w.sv, n1, sid)
    with pytest.raises(AppError) as exc:
        svc.start_session(w.sv, n1, uuid4())
    assert exc.value.code == "SESSION_IN_PROGRESS" and exc.value.details["sessionId"] == str(sid)
    svc.apply_result(result(w, tree, "n1_bien_bo_nho", sid, Verdict.PASSED, 80))
    with pytest.raises(AppError) as exc:
        svc.start_session(w.sv, n1, uuid4())
    assert exc.value.code == "NODE_ALREADY_MASTERED"


def test_abandon_returns_to_available_or_not_passed(published):
    w, tree, svc = published
    n1 = node_id(tree, "n1_bien_bo_nho")
    sid = new_session(w, tree, "n1_bien_bo_nho")
    svc.start_session(w.sv, n1, sid)
    assert svc.abandon(w.sv, n1, sid).state == S.AVAILABLE, "chưa từng trượt"
    sid2 = new_session(w, tree, "n1_bien_bo_nho")
    svc.start_session(w.sv, n1, sid2)
    svc.apply_result(result(w, tree, "n1_bien_bo_nho", sid2, Verdict.FAILED, 30))
    rec = w.db.query(MasteryRecord).filter_by(student_id=w.sv, node_id=n1).one()
    rec.last_failed_at = datetime.now(UTC) - timedelta(minutes=11)
    w.db.flush()
    sid3 = new_session(w, tree, "n1_bien_bo_nho")
    svc.start_session(w.sv, n1, sid3)
    assert svc.abandon(w.sv, n1, sid3).state == S.NOT_PASSED, "đã từng trượt"


def test_abandon_keeps_cooldown_and_reverify(published):
    """Bỏ dở không làm mới thời gian chờ; bỏ dở phiên xác nhận lại thì quay về NEEDS_REVERIFY."""
    w, tree, svc = published
    n1 = node_id(tree, "n1_bien_bo_nho")
    sid = new_session(w, tree, "n1_bien_bo_nho")
    svc.start_session(w.sv, n1, sid)
    svc.apply_result(result(w, tree, "n1_bien_bo_nho", sid, Verdict.FAILED, 30))
    rec = w.db.query(MasteryRecord).filter_by(student_id=w.sv, node_id=n1).one()
    rec.last_failed_at = datetime.now(UTC) - timedelta(minutes=11)
    w.db.flush()
    sid2 = new_session(w, tree, "n1_bien_bo_nho")
    svc.start_session(w.sv, n1, sid2)
    p = svc.abandon(w.sv, n1, sid2)
    assert p.state == S.NOT_PASSED and p.can_start is True and p.retry_at is None
    rec = w.db.query(MasteryRecord).filter_by(student_id=w.sv, node_id=n1).one()
    rec.state = S.NEEDS_REVERIFY
    w.db.flush()
    sid3 = new_session(w, tree, "n1_bien_bo_nho")
    svc.start_session(w.sv, n1, sid3)
    assert svc.abandon(w.sv, n1, sid3).state == S.NEEDS_REVERIFY


# --- Phát hành phiên bản mới (Xong khi 2, BR-14) -------------------------------------------------


def _new_version(w):
    r = w.api.post(f"/api/v1/classes/{w.class_id}/tree-versions")
    assert r.status_code == 201, r.text
    return r.json()


def _publish(w, v):
    r = w.api.post(f"/api/v1/tree-versions/{v['id']}/publish")
    assert r.status_code == 200, r.text
    return r.json()


def test_new_version_keeps_states(published, events):
    w, tree, svc = published
    pass_node(svc, w, tree, "n1_bien_bo_nho", 77)
    v2 = _publish(w, _new_version(w))
    m = svc.my_map(w.class_id, w.sv)
    assert m.tree.version_no == 2
    st = {p.node_key: p for p in m.progress}
    assert st["n1_bien_bo_nho"].state == S.MASTERED and st["n1_bien_bo_nho"].best_score == 77
    assert st["n1_bien_bo_nho"].attempts == 1
    assert st["n2_mang"].state == S.AVAILABLE and st["n5_con_tro"].state == S.LOCKED
    assert st["n1_bien_bo_nho"].node_id == node_id(v2, "n1_bien_bo_nho") != node_id(tree, "n1_bien_bo_nho")


def test_new_version_br14_reverify_and_relock(published, events):
    w, tree, svc = published
    pass_node(svc, w, tree, "n1_bien_bo_nho")
    draft = _new_version(w)
    # N1 đổi rubric ⇒ MASTERED → NEEDS_REVERIFY
    rubric = next(n["rubric"] for n in draft["nodes"] if n["key"] == "n1_bien_bo_nho")
    rubric = rubric | {"passThreshold": 80, "approved": True}
    assert w.api.put(f"/api/v1/nodes/{node_id(draft, 'n1_bien_bo_nho')}/rubric", json=rubric).status_code == 200
    # N3 (đang AVAILABLE) có thêm tiên quyết N2 chưa Đạt ⇒ LOCKED
    e = w.api.post(f"/api/v1/tree-versions/{draft['id']}/edges", json={"fromKey": "n2_mang", "toKey": "n3_ham_tham_so"})
    assert e.status_code == 201
    _publish(w, draft)
    st = states(svc, w, tree)
    assert st["n1_bien_bo_nho"] == S.NEEDS_REVERIFY
    assert st["n3_ham_tham_so"] == S.LOCKED
    assert st["n2_mang"] == S.AVAILABLE, "tiên quyết NEEDS_REVERIFY vẫn tính là đã Đạt"
    mig = {e.node_key: e for e in events if e.reason == MasteryChangeReason.PUBLISH_MIGRATE}
    assert mig["n1_bien_bo_nho"].old_state == S.MASTERED and mig["n3_ham_tham_so"].new_state == S.LOCKED
    # NEEDS_REVERIFY bắt đầu phiên xác nhận được
    sid = new_session(w, svc.my_map(w.class_id, w.sv).tree.model_dump(mode="json", by_alias=True), "n1_bien_bo_nho")
    v2 = svc.my_map(w.class_id, w.sv).tree
    assert (
        svc.start_session(w.sv, next(n.id for n in v2.nodes if n.key == "n1_bien_bo_nho"), sid).state == S.IN_PROGRESS
    )


def test_result_for_old_version_node_lands_on_current_version(published):
    """Phiên bắt đầu ở v1, GV phát hành v2 giữa chừng: kết quả ghi vào nút cùng key ở v2."""
    w, tree, svc = published
    n1_v1 = node_id(tree, "n1_bien_bo_nho")
    sid = new_session(w, tree, "n1_bien_bo_nho")
    svc.start_session(w.sv, n1_v1, sid)
    _publish(w, _new_version(w))
    ev = svc.apply_result(result(w, tree, "n1_bien_bo_nho", sid, Verdict.PASSED, 88))
    assert ev.node_id != n1_v1 and ev.node_key == "n1_bien_bo_nho"
    assert states(svc, w, tree)["n2_mang"] == S.AVAILABLE


def test_late_result_of_abandoned_session_is_ignored(published):
    """Phiên A hết hạn (abandon) rồi kết quả A về muộn: không ghi; SV đã mở phiên B thì A không đè lên B."""
    w, tree, svc = published
    n1 = node_id(tree, "n1_bien_bo_nho")
    a = new_session(w, tree, "n1_bien_bo_nho")
    svc.start_session(w.sv, n1, a)
    svc.abandon(w.sv, n1, a)
    assert svc.apply_result(result(w, tree, "n1_bien_bo_nho", a, Verdict.PASSED, 90)) is None
    assert states(svc, w, tree)["n1_bien_bo_nho"] == S.AVAILABLE
    b = new_session(w, tree, "n1_bien_bo_nho")
    svc.start_session(w.sv, n1, b)
    assert svc.apply_result(result(w, tree, "n1_bien_bo_nho", a, Verdict.FAILED, 10)) is None
    ev = svc.apply_result(result(w, tree, "n1_bien_bo_nho", b, Verdict.PASSED, 85))
    assert ev is not None and ev.session_id == b
    p1 = next(p for p in svc.my_map(w.class_id, w.sv).progress if p.node_key == "n1_bien_bo_nho")
    assert p1.attempts == 1 and p1.best_score == 85


def test_rejected_start_does_not_commit_callers_session(published):
    """start_session bị 409 không commit giao dịch của bên gọi – TeachingSession vừa tạo rollback được."""
    w, tree, svc = published
    sid = new_session(w, tree, "n5_con_tro")
    with pytest.raises(AppError):
        svc.start_session(w.sv, node_id(tree, "n5_con_tro"), sid)
    w.db.rollback()
    assert w.db.get(TeachingSession, sid) is None


@pytest.mark.parametrize("key", ["n1_bien_bo_nho", "n5_con_tro"])
def test_can_start_does_not_commit_callers_session(published, key):
    """Kiểm tra trước khi mở phiên không được commit TeachingSession của bên gọi, kể cả khi bị chặn."""
    w, tree, svc = published
    sid = new_session(w, tree, key)
    check = svc.can_start(w.sv, node_id(tree, key))
    assert check.allowed is (key == "n1_bien_bo_nho")
    w.db.rollback()
    assert w.db.get(TeachingSession, sid) is None


def test_can_start_initialisation_is_temporary_until_start(published, events):
    """Ô thiếu chỉ được ghi / phát sự kiện khi bắt đầu thật; kiểm tra không mất thay đổi đang chờ của bên gọi."""
    w, tree, svc = published
    w.db.query(MasteryRecord).filter_by(student_id=w.sv).delete()
    w.db.commit()
    events.clear()
    sid = new_session(w, tree, "n1_bien_bo_nho")
    assert svc.can_start(w.sv, node_id(tree, "n1_bien_bo_nho")).allowed
    assert w.db.query(MasteryRecord).filter_by(student_id=w.sv).count() == 0
    assert w.db.get(TeachingSession, sid) is not None
    assert not events
    svc.start_session(w.sv, node_id(tree, "n1_bien_bo_nho"), sid)
    assert w.db.query(MasteryRecord).filter_by(student_id=w.sv).count() == 11
    assert len([e for e in events if e.reason == MasteryChangeReason.PUBLISH_INIT]) == 11


def test_result_without_start_after_failure_is_logged_and_ignored(published, caplog):
    w, tree, svc = published
    key = "n1_bien_bo_nho"
    sid = new_session(w, tree, key)
    svc.start_session(w.sv, node_id(tree, key), sid)
    svc.apply_result(result(w, tree, key, sid, Verdict.FAILED, 30))
    unstarted = new_session(w, tree, key)
    assert svc.apply_result(result(w, tree, key, unstarted, Verdict.PASSED, 90)) is None
    p = next(p for p in svc.my_map(w.class_id, w.sv).progress if p.node_key == key)
    assert (p.state, p.attempts, p.best_score, p.last_session_id) == (S.NOT_PASSED, 1, 30, sid)
    assert any(
        r.levelname == "ERROR" and str(unstarted) in r.getMessage() and "NOT_PASSED" in r.getMessage()
        for r in caplog.records
    )


def test_concurrent_my_maps_initialise_each_cell_once(committed_world):
    engine, w, user = committed_world
    tree = draft(engine, w, user)
    bus = InMemoryEventBus()
    with Session(engine) as db:
        SkillTreeService(db).publish(tree.id, user)
        db.execute(delete(MasteryRecord).where(MasteryRecord.class_id == w.class_id))
        db.commit()
    both_read = Barrier(2)

    class ConcurrentMap(MasteryService):
        def _require_enrolled(self, *args):
            both_read.wait(timeout=5)
            return super()._require_enrolled(*args)

    def read_map():
        with Session(engine) as db:
            return ConcurrentMap(db, bus=bus).my_map(w.class_id, w.sv)

    with ThreadPoolExecutor(max_workers=2) as pool:
        maps = list(pool.map(lambda _: read_map(), range(2)))
    assert all(len(m.progress) == 2 for m in maps)
    with Session(engine) as db:
        rows = list(db.scalars(select(MasteryRecord).where(MasteryRecord.class_id == w.class_id)))
        assert len(rows) == 2 and {r.node_id for r in rows} == {n.id for n in tree.nodes}


@pytest.mark.parametrize("operation", ["my_map", "ensure_student", "abandon"])
def test_mastery_waiting_for_publish_does_not_migrate_backwards(committed_world, operation):
    engine, w, user = committed_world
    v1 = draft(engine, w, user)
    bus = InMemoryEventBus()
    with Session(engine) as db:
        SkillTreeService(db).publish(v1.id, user)
        v2 = SkillTreeService(db).create_version(w.class_id, user)
    read_old_tree, release = Event(), Event()

    class PausedMap(MasteryService):
        def _require_enrolled(self, *args):
            read_old_tree.set()
            assert release.wait(5)
            return super()._require_enrolled(*args)

    def read_map():
        with Session(engine) as db:
            service = PausedMap(db, bus=bus)
            if operation == "abandon":
                return service.abandon(w.sv, v1.nodes[0].id, uuid4())
            return getattr(service, operation)(w.class_id, w.sv)

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(read_map)
        try:
            assert read_old_tree.wait(5)
            with Session(engine) as db:
                SkillTreeService(db).publish(v2.id, user)
        finally:
            release.set()
        m = pending.result(timeout=5)
    with Session(engine) as db:
        rows = list(db.scalars(select(MasteryRecord).where(MasteryRecord.class_id == w.class_id)))
        assert {r.node_id for r in rows} == {n.id for n in v2.nodes}
    if operation == "my_map":
        assert m.tree.id == v2.id


def test_my_map_keeps_consistent_snapshot_when_publish_follows_commit(committed_world):
    engine, w, user = committed_world
    v1 = draft(engine, w, user)
    bus = InMemoryEventBus()
    with Session(engine) as db:
        SkillTreeService(db).publish(v1.id, user)
        v2 = SkillTreeService(db).create_version(w.class_id, user)

    class PublishAfterCommit(MasteryService):
        def _commit(self, changes):
            result = super()._commit(changes)
            with Session(engine) as other:
                SkillTreeService(other).publish(v2.id, user)
            return result

    with Session(engine) as db:
        m = PublishAfterCommit(db, bus=bus).my_map(w.class_id, w.sv)
    assert m.tree.id == v1.id
    assert {p.node_id for p in m.progress} == {n.id for n in v1.nodes}
