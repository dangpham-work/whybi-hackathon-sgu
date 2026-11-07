"""KT-11 (#50) – FR-HM-03 / NFR-03: SV xong phiên ⇒ bản đồ nhiệt của GV đổi màu ≤ 3 giây.

Đo từ lúc phát `session.completed` tới Probe trong Hub của kênh `class:{id}:heatmap` nhận ĐỦ hai tin:
`heatmap.cell` (ô SV × nút đã đổi trạng thái) và `heatmap.node` (màu nút mới). Chuỗi chạy là code thật:

    session.completed → MasteryService.apply_result (commit CSDL) → mastery.changed
      → heatmap.register_handlers → task aggregation.push_cell / recompute_node (+ truy vết gốc) → gateway.broadcast

- Chế độ `memory`: InMemoryEventBus, gateway giao thẳng cho hub – cần `TEST_DATABASE_URL` (CI job backend có).
- Chế độ `redis`: RedisEventBus thật cho cả hai chủ đề + RedisRelay "ws:*" như tiến trình api – cần thêm
  `TEST_REDIS_URL` (vd. redis://localhost:6381/0). CI job backend chưa đặt biến này ⇒ bỏ qua ở CI.
- Probe thay kết nối WebSocket: không mở socket mạng và không đo render UI.
- Task Celery được GỌI TRỰC TIẾP trong luồng nghe sự kiện (như chế độ eager): không đo thời gian xếp hàng của
  worker Celery. Phần đó đo trên stack thật ở `e2e/tests/mx3-heatmap-realtime.spec.ts` (job CI `e2e`).
"""

import json
import os
import queue
import time
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.models.enums import HeatColor, MasteryState, Role, Verdict
from app.models.schemas.mastery import TOPIC_SESSION_COMPLETED
from app.models.schemas.session import SessionResult
from app.models.session import TeachingSession
from app.models.users import ClassSection, Enrollment, Student, User
from app.realtime import gateway
from app.realtime.bus import InMemoryEventBus, RedisEventBus
from app.services import heatmap, mastery
from app.services.mastery import MasteryService
from app.services.skill_tree import SkillTreeService
from app.workers import aggregation
from tests.unit import test_tree_concurrency_db as _c209
from tests.unit.test_tree_edit_db import DB_URL

committed_world = _c209.committed_world

REDIS_URL = os.getenv("TEST_REDIS_URL")
GIOI_HAN_GIAY = 3.0  # FR-HM-03, NFR-03

pytestmark = pytest.mark.skipif(not DB_URL, reason="đặt TEST_DATABASE_URL để chạy trên Postgres thật")

# Kết quả lần lượt của 4 SV ở cùng một nút, cỡ mẫu tối thiểu = 1, ngưỡng mặc định xanh 0,7 / vàng 0,4:
# 1/1 = 100% XANH → 1/2 = 50% VÀNG → 1/3 = 33% ĐỎ → 2/4 = 50% VÀNG – lần nào màu cũng đổi.
KICH_BAN = [
    (True, HeatColor.GREEN),
    (False, HeatColor.YELLOW),
    (False, HeatColor.RED),
    (True, HeatColor.YELLOW),
]


class Probe:
    """Đứng thay một kết nối WebSocket của GV trong Hub (Hub chỉ gọi `push(tin đã mã hóa)`)."""

    def __init__(self) -> None:
        self.inbox: queue.Queue[dict] = queue.Queue()

    def push(self, message: str) -> None:
        self.inbox.put(json.loads(message))

    def wait_for(self, done, deadline: float) -> list[dict]:
        """Đọc tin tới khi `done(tin đã nhận)` đúng hoặc hết hạn. Trả mọi tin đã nhận."""
        got: list[dict] = []
        while not done(got):
            left = deadline - time.perf_counter()
            if left <= 0:
                break
            try:
                got.append(self.inbox.get(timeout=left))
            except queue.Empty:
                break
        return got


@pytest.fixture
def lop(committed_world):
    """Lớp đã commit: 4 SV, cây 2 nút đã phát hành, cỡ mẫu tối thiểu 1 (để 1 SV đã đủ đổi màu)."""
    engine, w, user = committed_world
    students = [w.sv]
    with Session(engine) as db:
        for i in range(len(KICH_BAN) - 1):
            u = User(
                id=uuid4(),
                full_name=f"SV KT-11 {i}",
                email=f"{uuid4().hex[:8]}@whybi.test",
                password_hash="x",
                role=Role.STUDENT,
            )
            db.add(u)
            db.flush()
            db.add(Student(user_id=u.id, student_code=uuid4().hex[:10]))
            db.flush()
            db.add(Enrollment(class_id=w.class_id, student_id=u.id))
            w.roles[u.id] = Role.STUDENT  # committed_world xóa mọi user trong w.roles khi dọn
            students.append(u.id)
        db.get(ClassSection, w.class_id).min_sample = 1
        db.commit()
    tree = _c209.draft(engine, w, user)
    with Session(engine) as db:
        SkillTreeService(db).publish(tree.id, user)
    return engine, w, students, tree.nodes[0].id


def bat_dau_phien(engine, w, student_id: UUID, node_id: UUID) -> UUID:
    """Orchestrator tạo phiên + start_session (ô → IN_PROGRESS). Bus riêng: không lẫn tin IN_PROGRESS vào phép đo."""
    sid = uuid4()
    with Session(engine) as db:
        db.add(
            TeachingSession(
                id=sid, student_id=student_id, node_id=node_id, class_id=w.class_id, input_mode="TEXT", status="CREATED"
            )
        )
        db.flush()
        MasteryService(db, bus=InMemoryEventBus()).start_session(student_id, node_id, sid)
    return sid


def ket_qua(w, sid: UUID, student_id: UUID, node_id: UUID, passed: bool) -> SessionResult:
    return SessionResult(
        session_id=sid,
        student_id=student_id,
        node_id=node_id,
        class_id=w.class_id,
        state=MasteryState.MASTERED if passed else MasteryState.NOT_PASSED,
        verdict=Verdict.PASSED if passed else Verdict.FAILED,
        total_score=80.0 if passed else 40.0,
        criteria=[],
    )


def noi_chuoi_su_kien(bus, engine, monkeypatch) -> None:
    """Đăng ký đúng các handler của tiến trình `mastery_listener` cho chuỗi heatmap; task Celery gọi trực tiếp."""
    monkeypatch.setattr(aggregation, "_session", lambda: Session(engine))
    mastery.register_handlers(bus, session_factory=lambda: Session(engine))
    heatmap.register_handlers(
        bus,
        enqueue=lambda class_id, node_id: aggregation.recompute_node(str(class_id), str(node_id)),
        cell=lambda event: aggregation.push_cell(event.model_dump_json(by_alias=True)),
    )


def do_tre(bus, probe: Probe, w, engine, students, node_id) -> list[float]:
    """Chạy KICH_BAN; mỗi lượt kiểm nội dung tin WebSocket và trả độ trễ (giây)."""
    node = str(node_id)
    latencies = []
    for i, (student_id, (passed, color)) in enumerate(zip(students, KICH_BAN, strict=True)):
        sid = bat_dau_phien(engine, w, student_id, node_id)
        state = (MasteryState.MASTERED if passed else MasteryState.NOT_PASSED).value

        def cell_ok(m, student=str(student_id), state=state):
            p = m["payload"]
            return m["event"] == "heatmap.cell" and p["studentId"] == student and p["state"] == state

        def node_ok(m, attempted=i + 1, color=color.value):
            p = m["payload"]
            return (
                m["event"] == "heatmap.node"
                and p["nodeId"] == node
                and p["attemptedCount"] == attempted
                and p["color"] == color
            )

        t0 = time.perf_counter()
        bus.publish(TOPIC_SESSION_COMPLETED, ket_qua(w, sid, student_id, node_id, passed))
        got = probe.wait_for(
            lambda ms, c=cell_ok, n=node_ok: any(map(c, ms)) and any(map(n, ms)), t0 + GIOI_HAN_GIAY + 2
        )
        elapsed = time.perf_counter() - t0
        assert any(map(cell_ok, got)), f"lượt {i + 1}: thiếu heatmap.cell {state} – nhận {got}"
        assert any(map(node_ok, got)), f"lượt {i + 1}: thiếu heatmap.node màu {color.value} – nhận {got}"
        assert all(m["channel"] == gateway.channel_heatmap(w.class_id) for m in got)
        latencies.append(elapsed)
    print(f"KT-11 độ trễ session.completed → heatmap.cell + heatmap.node (giây): {[round(x, 3) for x in latencies]}")
    return latencies


def test_mt_doi_mau_duoi_3_giay_bus_trong_tien_trinh(lop, monkeypatch):
    engine, w, students, node_id = lop
    bus = InMemoryEventBus()
    noi_chuoi_su_kien(bus, engine, monkeypatch)
    monkeypatch.setattr(gateway, "_in_process", lambda: True)
    probe = Probe()
    channel = gateway.channel_heatmap(w.class_id)
    gateway.hub.subscribe(channel, probe)
    try:
        latencies = do_tre(bus, probe, w, engine, students, node_id)
    finally:
        gateway.hub.unsubscribe(channel, probe)
    assert max(latencies) <= GIOI_HAN_GIAY, f"độ trễ từng lượt (giây): {latencies}"


@pytest.mark.skipif(not REDIS_URL, reason="đặt TEST_REDIS_URL để đo qua Redis Pub/Sub thật")
def test_mt_doi_mau_duoi_3_giay_qua_redis_that(lop, monkeypatch):
    import redis

    engine, w, students, node_id = lop
    client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    monkeypatch.setattr(gateway, "_in_process", lambda: False)  # worker → Redis "ws:<kênh>" → api
    monkeypatch.setattr(gateway, "_redis", lambda: client)
    bus = RedisEventBus(REDIS_URL)
    noi_chuoi_su_kien(bus, engine, monkeypatch)
    hub = gateway.Hub()  # hub riêng của "tiến trình api" trong test
    probe = Probe()
    hub.subscribe(gateway.channel_heatmap(w.class_id), probe)
    relay = gateway.RedisRelay(redis_url=REDIS_URL, target=hub)
    relay.start()
    bus.start()
    try:
        latencies = do_tre(bus, probe, w, engine, students, node_id)
    finally:
        bus.stop()
        relay.stop()
        client.close()
    assert max(latencies) <= GIOI_HAN_GIAY, f"độ trễ từng lượt (giây): {latencies}"
