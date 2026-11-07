"""C2-11 – Xong khi (CSDL thật): lớp 30 SV học qua MasteryService ⇒ class_node_stats ra đúng màu 6.5.2.

Luồng thật: phát hành cây → start_session / apply_result → mastery.changed → hàng đợi (đồng bộ trong test)
→ HeatmapService.recompute → class_node_stats. Cần Postgres đã migrate (TEST_DATABASE_URL).
"""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import HeatColor, HeatSample, MasteryState, Role, Verdict
from app.models.peer import ClassNodeStat
from app.models.schemas.session import SessionResult
from app.models.session import TeachingSession
from app.models.users import Enrollment, Student, User
from app.realtime.bus import InMemoryEventBus
from app.services import heatmap
from app.services.heatmap import HeatmapService
from app.services.mastery import MasteryService
from app.services.skill_tree import SkillTreeService
from tests.unit import test_tree_concurrency_db as _concurrent
from tests.unit import test_tree_edit_db as _c209
from tests.unit.test_tree_concurrency_db import draft
from tests.unit.test_tree_edit_db import DB_URL, _approve_all, _import_seed

world = _c209.world
committed_world = _concurrent.committed_world

pytestmark = pytest.mark.skipif(not DB_URL, reason="đặt TEST_DATABASE_URL để chạy trên Postgres thật")


@pytest.fixture
def lop30(world, monkeypatch):
    """Lớp 30 SV (SV của World + 29 SV mới), cây mẫu đã phát hành, heatmap nghe mastery.changed đồng bộ."""
    import app.services.mastery as mastery_mod

    w = world
    bus = InMemoryEventBus()
    monkeypatch.setattr(mastery_mod, "get_bus", lambda: bus)
    queued: list[tuple[UUID, UUID]] = []

    def run_now(class_id: UUID, node_id: UUID) -> None:
        queued.append((class_id, node_id))
        HeatmapService(w.db).recompute(class_id, node_id)

    heatmap.register_handlers(bus, enqueue=run_now)
    students = [w.sv]
    for i in range(29):
        u = User(
            id=uuid4(), full_name=f"SV {i}", email=f"{uuid4().hex[:8]}@whybi.test", password_hash="x", role=Role.STUDENT
        )
        w.db.add(u)
        w.db.flush()
        w.db.add(Student(user_id=u.id, student_code=uuid4().hex[:10]))
        w.db.flush()
        w.db.add(Enrollment(class_id=w.class_id, student_id=u.id))
        students.append(u.id)
    w.db.flush()
    tv = _import_seed(w)
    _approve_all(w, tv)
    r = w.api.post(f"/api/v1/tree-versions/{tv['id']}/publish")
    assert r.status_code == 200, r.text
    tree = r.json()
    ids = {n["key"]: UUID(n["id"]) for n in tree["nodes"]}
    return w, MasteryService(w.db, bus=bus), students, ids, queued


def hoc(w, svc: MasteryService, sv: UUID, node_id: UUID, passed: bool) -> None:
    s = TeachingSession(
        id=uuid4(), student_id=sv, node_id=node_id, class_id=w.class_id, input_mode="TEXT", status="CREATED"
    )
    w.db.add(s)
    w.db.flush()
    svc.start_session(sv, node_id, s.id)
    svc.apply_result(
        SessionResult(
            session_id=s.id,
            student_id=sv,
            node_id=node_id,
            class_id=w.class_id,
            state=MasteryState.MASTERED if passed else MasteryState.NOT_PASSED,
            verdict=Verdict.PASSED if passed else Verdict.FAILED,
            total_score=80.0 if passed else 40.0,
            criteria=[],
        )
    )


def stats(w, ids) -> dict[str, ClassNodeStat]:
    key_of = {v: k for k, v in ids.items()}
    rows = w.db.scalars(
        select(ClassNodeStat).where(ClassNodeStat.class_id == w.class_id).execution_options(populate_existing=True)
    )
    return {key_of[r.node_id]: r for r in rows if r.node_id in key_of}


def test_lop_30_sv_ra_dung_mau_tren_csdl(lop30):
    w, svc, sv, ids, _ = lop30
    # Ngay sau phát hành: mọi nút XÁM vì chưa ai thử, sĩ số 30
    st = stats(w, ids)
    assert len(st) == 11 and all(s.color == HeatColor.GREY and s.enrolled_count == 30 for s in st.values())

    # n1: 21 Đạt / 9 Chưa đạt = đúng 70% ⇒ XANH (biên)
    for i, s in enumerate(sv):
        hoc(w, svc, s, ids["n1_bien_bo_nho"], passed=i < 21)
    passers = sv[:21]
    # n2: 10 SV thử, 5 Đạt = 50% ⇒ VÀNG
    for i, s in enumerate(passers[:10]):
        hoc(w, svc, s, ids["n2_mang"], passed=i < 5)
    # n3: 6 SV thử, 2 Đạt = 33% ⇒ ĐỎ (đủ mẫu, chưa đạt)
    for i, s in enumerate(passers[10:16]):
        hoc(w, svc, s, ids["n3_ham_tham_so"], passed=i < 2)
    # n5 (cần n1 + n3): 2 SV thử, cả 2 Đạt ⇒ XÁM vì chưa đủ mẫu (không phải XANH)
    for s in passers[10:12]:
        hoc(w, svc, s, ids["n5_con_tro"], passed=True)

    st = stats(w, ids)
    n1, n2, n3, n4, n5 = (st[k] for k in ("n1_bien_bo_nho", "n2_mang", "n3_ham_tham_so", "n4_de_quy", "n5_con_tro"))
    assert (n1.color, n1.attempted_count, n1.passed_count) == (HeatColor.GREEN, 30, 21)
    assert n1.pass_rate == pytest.approx(0.7)
    assert (n2.color, n2.attempted_count, n2.passed_count) == (HeatColor.YELLOW, 10, 5)
    assert (n3.color, n3.attempted_count, n3.passed_count) == (HeatColor.RED, 6, 2)
    assert (n5.color, n5.attempted_count, n5.passed_count) == (HeatColor.GREY, 2, 2)
    assert (n4.color, n4.attempted_count, n4.pass_rate) == (HeatColor.GREY, 0, None)  # mở khóa nhưng chưa ai thử

    # GV đổi cỡ mẫu tối thiểu xuống 2 ⇒ đối soát cả lớp thì n5 thành XANH
    from app.models.users import ClassSection

    w.db.get(ClassSection, w.class_id).min_sample = 2
    nodes = {n.node_key: n for n in HeatmapService(w.db).recompute_class(w.class_id)}
    assert len(nodes) == 11
    assert nodes["n5_con_tro"].color == HeatColor.GREEN and nodes["n5_con_tro"].sample == HeatSample.SUFFICIENT
    assert nodes["n4_de_quy"].sample == HeatSample.NO_ATTEMPT and nodes["n4_de_quy"].label == "Chưa có SV nào thử"
    assert stats(w, ids)["n5_con_tro"].color == HeatColor.GREEN


def test_chi_tinh_lai_nut_bi_anh_huong(lop30):
    """6.5.1: một lượt chấm chỉ đẩy đúng nút đó; bắt đầu phiên và mở khóa nút con không đẩy việc."""
    w, svc, sv, ids, queued = lop30
    queued.clear()
    hoc(w, svc, sv[0], ids["n1_bien_bo_nho"], passed=True)
    assert queued == [(w.class_id, ids["n1_bien_bo_nho"])]


def test_sv_roi_lop_khong_con_tinh(lop30):
    w, svc, sv, ids, _ = lop30
    hoc(w, svc, sv[1], ids["n1_bien_bo_nho"], passed=False)
    w.db.execute(Enrollment.__table__.delete().where(Enrollment.student_id == sv[1]))
    node = HeatmapService(w.db).recompute(w.class_id, ids["n1_bien_bo_nho"])
    assert node.enrolled_count == 29 and node.attempted_count == 0


def test_nut_khong_thuoc_ban_phat_hanh_bi_bo_qua(lop30):
    w, *_ = lop30
    assert HeatmapService(w.db).recompute(w.class_id, uuid4()) is None


def test_published_class_ids(lop30):
    w, *_ = lop30
    assert w.class_id in HeatmapService(w.db).published_class_ids()
    assert w.class_id in SkillTreeService(w.db).published_class_ids()


def test_nguong_mau_lay_qua_class_service(world):
    """Ranh giới service: HeatmapService đọc ngưỡng màu qua ClassService, không đọc thẳng class_sections."""
    from app.algorithms.heatmap import ColorRule
    from app.core.errors import AppError
    from app.models.users import ClassSection
    from app.services.classes import ClassService

    w = world
    cls = w.db.get(ClassSection, w.class_id)
    cls.color_thresholds = {"green": 0.9, "yellow": 0.5}
    cls.min_sample = 7
    w.db.flush()
    expected = ColorRule(green=0.9, yellow=0.5, min_sample=7)
    assert ClassService(w.db).color_rule(w.class_id) == expected
    assert HeatmapService(w.db).rule(w.class_id) == expected
    with pytest.raises(AppError) as e:
        ClassService(w.db).color_rule(uuid4())
    assert e.value.status == 404 and e.value.code == "CLASS_NOT_FOUND"


def test_phat_hanh_lai_khong_doi_trang_thai_van_tong_hop_nut_moi(lop30):
    """Đổi node_id dù trạng thái giữ nguyên vẫn phải có thống kê bản đang phát hành."""
    w, svc, sv, ids, _ = lop30
    hoc(w, svc, sv[0], ids["n1_bien_bo_nho"], passed=True)
    old = stats(w, ids)
    expected = {k: (s.enrolled_count, s.attempted_count, s.passed_count, s.color) for k, s in old.items()}

    tv = _import_seed(w)
    _approve_all(w, tv)
    response = w.api.post(f"/api/v1/tree-versions/{tv['id']}/publish")
    assert response.status_code == 200, response.text
    new_ids = {n["key"]: UUID(n["id"]) for n in response.json()["nodes"]}
    assert set(new_ids.values()).isdisjoint(ids.values())
    actual = stats(w, new_ids)
    assert set(actual) == set(new_ids), "Nút mới thiếu thống kê sau phát hành, không được chờ beat 10 phút"
    assert {k: (s.enrolled_count, s.attempted_count, s.passed_count, s.color) for k, s in actual.items()} == expected


def test_phat_hanh_lop_chua_co_sv_van_co_thong_ke(world):
    w = world
    w.db.execute(Enrollment.__table__.delete().where(Enrollment.class_id == w.class_id))
    tv = _import_seed(w)
    _approve_all(w, tv)
    response = w.api.post(f"/api/v1/tree-versions/{tv['id']}/publish")
    assert response.status_code == 200, response.text
    ids = {n["key"]: UUID(n["id"]) for n in response.json()["nodes"]}
    actual = stats(w, ids)
    assert set(actual) == set(ids)
    assert all(s.enrolled_count == s.attempted_count == s.passed_count == 0 for s in actual.values())


@pytest.mark.parametrize("slow_class", [False, True], ids=["slow-node", "slow-class"])
@pytest.mark.parametrize("fast_class", [False, True], ids=["fast-node", "fast-class"])
def test_tong_hop_cham_khong_ghi_de_anh_chup_moi(committed_world, monkeypatch, slow_class, fast_class):
    """Worker cũ dừng sau đọc; worker mới chạy sau kết quả Đạt phải thắng cả đối soát lớp."""
    engine, w, user = committed_world
    tree = draft(engine, w, user)
    bus = InMemoryEventBus()
    monkeypatch.setattr("app.services.mastery.get_bus", lambda: bus)
    with Session(engine) as db:
        SkillTreeService(db).publish(tree.id, user)
    node_id = tree.nodes[0].id
    read_old, release, fast_done = Event(), Event(), Event()
    original = MasteryService.columns

    def paused_columns(service, *args, **kwargs):
        cols = original(service, *args, **kwargs)
        if service.db.info.pop("slow_heatmap", False):
            read_old.set()
            assert release.wait(5)
        return cols

    monkeypatch.setattr(MasteryService, "columns", paused_columns)

    def recompute(slow, whole_class):
        try:
            with Session(engine) as db:
                db.info["slow_heatmap"] = slow
                svc = HeatmapService(db)
                if whole_class:
                    svc.recompute_class(w.class_id)
                else:
                    svc.recompute(w.class_id, node_id)
                db.commit()
        finally:
            if not slow:
                fast_done.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(recompute, True, slow_class)
        try:
            assert read_old.wait(5)
            with Session(engine) as db:
                hoc(SimpleNamespace(db=db, class_id=w.class_id), MasteryService(db, bus=bus), w.sv, node_id, True)
            second = pool.submit(recompute, False, fast_class)
            fast_done.wait(0.5)
        finally:
            release.set()
        first.result(timeout=5)
        second.result(timeout=5)

    with Session(engine) as db:
        row = db.scalar(
            select(ClassNodeStat).where(ClassNodeStat.class_id == w.class_id, ClassNodeStat.node_id == node_id)
        )
        assert (row.enrolled_count, row.attempted_count, row.passed_count) == (1, 1, 1)


def test_nut_ban_phat_hanh_lay_qua_skill_tree_service(lop30):
    """MasteryService.columns lấy (id → key) bản đang phát hành qua SkillTreeService, không đọc thẳng bảng cây."""
    from app.core.errors import AppError

    w, _, _, ids, _ = lop30
    svc = SkillTreeService(w.db)
    keys = svc.published_node_keys(w.class_id)
    assert keys == {i: k for k, i in sorted(ids.items())}
    assert list(keys.values()) == sorted(keys.values())
    some = next(iter(ids.values()))
    assert svc.published_node_keys(w.class_id, [some, uuid4()]) == {some: keys[some]}
    with pytest.raises(AppError) as e:
        svc.published_node_keys(uuid4())
    assert e.value.status == 404 and e.value.code == "CLASS_NOT_FOUND"
