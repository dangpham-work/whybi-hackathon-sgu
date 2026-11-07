"""C2-11 – Xong khi: dữ liệu giả lập 30 SV ra đúng màu theo quy tắc 6.5.2 (Bảng 6.6).

Hàm thuần `app.algorithms.heatmap` – không cần CSDL. Bản chạy trên Postgres thật: test_heatmap_db.py.
"""

from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.algorithms.heatmap import Cell, ColorRule, aggregate, classify
from app.models.enums import HeatColor, HeatSample, MasteryChangeReason, MasteryState
from app.models.schemas.mastery import TOPIC_MASTERY_CHANGED, MasteryChanged
from app.realtime.bus import InMemoryEventBus
from app.services.heatmap import node_payload, register_handlers

S = MasteryState
SI_SO = 30


def lop(passed: int, failed: int, *, reverify: int = 0, in_progress_after_fail: int = 0) -> list[Cell]:
    """Một cột của ma trận cho lớp 30 SV: `passed` Đạt, `failed` Chưa đạt, phần còn lại chưa thử
    (một nửa LOCKED, một nửa AVAILABLE, vài SV đang giảng lần đầu)."""
    cells = [Cell(S.MASTERED, attempts=1) for _ in range(passed)]
    cells += [Cell(S.NOT_PASSED, attempts=2) for _ in range(failed)]
    cells += [Cell(S.NEEDS_REVERIFY, attempts=1) for _ in range(reverify)]
    cells += [Cell(S.IN_PROGRESS, attempts=1, prev_state=S.NOT_PASSED) for _ in range(in_progress_after_fail)]
    rest = SI_SO - len(cells)
    assert rest >= 0
    cells += [Cell(S.IN_PROGRESS, attempts=0, prev_state=S.AVAILABLE) for _ in range(min(rest, 2))]
    rest = SI_SO - len(cells)
    cells += [Cell(S.LOCKED, attempts=0) for _ in range(rest // 2)]
    cells += [Cell(S.AVAILABLE, attempts=0) for _ in range(SI_SO - len(cells))]
    assert len(cells) == SI_SO
    return cells


# key nút → (cột 30 SV, màu mong đợi, số đã thử, số Đạt, trạng thái mẫu)
LOP_30_SV = {
    "n1_vung": (lop(27, 3), HeatColor.GREEN, 30, 27, HeatSample.SUFFICIENT),
    "n2_bien_70": (lop(21, 9), HeatColor.GREEN, 30, 21, HeatSample.SUFFICIENT),  # đúng 70% ⇒ XANH
    "n3_duoi_70": (lop(20, 9), HeatColor.YELLOW, 29, 20, HeatSample.SUFFICIENT),  # 68,97%
    "n4_bien_40": (lop(8, 12), HeatColor.YELLOW, 20, 8, HeatSample.SUFFICIENT),  # đúng 40% ⇒ VÀNG
    "n5_nghen": (lop(2, 7), HeatColor.RED, 9, 2, HeatSample.SUFFICIENT),  # 22% – N5 ở Hình 6.9
    "n6_du_mau_0_dat": (lop(0, 5), HeatColor.RED, 5, 0, HeatSample.SUFFICIENT),  # đúng cỡ mẫu 5, 0% ⇒ ĐỎ
    "n7_thieu_mau": (lop(4, 0), HeatColor.GREY, 4, 4, HeatSample.INSUFFICIENT),  # 4 < 5 dù 100% Đạt
    "n8_thieu_mau_truot": (lop(0, 4), HeatColor.GREY, 4, 0, HeatSample.INSUFFICIENT),  # chưa đủ mẫu ≠ chưa đạt
    "n9_chua_ai_thu": (lop(0, 0), HeatColor.GREY, 0, 0, HeatSample.NO_ATTEMPT),
    # NEEDS_REVERIFY tính là Đạt (BR-02, như MasteryService); đang giảng lại sau Chưa đạt vẫn tính đã thử, chưa Đạt
    "n10_xac_nhan_lai": (
        lop(14, 2, reverify=7, in_progress_after_fail=7),
        HeatColor.GREEN,
        30,
        21,
        HeatSample.SUFFICIENT,
    ),
}


@pytest.mark.parametrize("key", list(LOP_30_SV))
def test_lop_30_sv_ra_dung_mau(key):
    cells, color, attempted, passed, sample = LOP_30_SV[key]
    st = aggregate(cells, enrolled=SI_SO, rule=ColorRule())
    assert st.color == color, key
    assert (st.attempted, st.passed, st.enrolled, st.sample) == (attempted, passed, SI_SO, sample)
    assert st.attempted_rate == pytest.approx(attempted / SI_SO)
    if attempted:
        assert st.pass_rate == pytest.approx(passed / attempted)
    else:
        assert st.pass_rate is None and st.avg_attempts is None


def test_tach_chua_du_mau_voi_chua_dat_bang_nhan_chu():
    """FR-HM-04: màu luôn kèm nhãn chữ; "chưa đủ mẫu" / "chưa ai thử" khác hẳn "điểm nghẽn"."""
    rule = ColorRule()
    nghen = aggregate(LOP_30_SV["n6_du_mau_0_dat"][0], SI_SO, rule)
    thieu = aggregate(LOP_30_SV["n8_thieu_mau_truot"][0], SI_SO, rule)
    chua_thu = aggregate(LOP_30_SV["n9_chua_ai_thu"][0], SI_SO, rule)
    assert nghen.label.startswith("✗") and "nghẽn" in nghen.label
    assert thieu.label == "Chưa đủ mẫu (4/5 SV đã thử)"
    assert chua_thu.label == "Chưa có SV nào thử"
    assert aggregate(LOP_30_SV["n1_vung"][0], SI_SO, rule).label.startswith("✓")
    assert aggregate(LOP_30_SV["n3_duoi_70"][0], SI_SO, rule).label.startswith("!")


def test_trung_binh_luot_chi_tinh_tren_sv_da_thu():
    st = aggregate([Cell(S.MASTERED, 1), Cell(S.NOT_PASSED, 3), Cell(S.AVAILABLE, 0)], enrolled=3, rule=ColorRule())
    assert st.avg_attempts == pytest.approx(2.0)


@pytest.mark.parametrize("attempts", [0, 1, 3])
def test_phien_cu_thieu_prev_state_khong_bien_lan_thu_cu_thanh_chua_thu(attempts):
    """Ô legacy đang giảng: attempts > 0 vẫn đã thử, nhưng không suy đoán là Đạt."""
    st = aggregate([Cell(S.IN_PROGRESS, attempts=attempts, prev_state=None)], enrolled=30, rule=ColorRule())
    assert st.attempted == int(attempts > 0)
    assert st.passed == 0
    assert st.sample == (HeatSample.INSUFFICIENT if attempts else HeatSample.NO_ATTEMPT)
    assert st.pass_rate == (0.0 if attempts else None)
    assert st.avg_attempts == (float(attempts) if attempts else None)


@pytest.mark.parametrize(
    ("before", "during", "after"),
    [
        (Cell(S.AVAILABLE), Cell(S.IN_PROGRESS, prev_state=S.AVAILABLE), Cell(S.AVAILABLE)),
        (Cell(S.NOT_PASSED, 2), Cell(S.IN_PROGRESS, 2, S.NOT_PASSED), Cell(S.NOT_PASSED, 2)),
        (Cell(S.NEEDS_REVERIFY, 1), Cell(S.IN_PROGRESS, 1, S.NEEDS_REVERIFY), Cell(S.NEEDS_REVERIFY, 1)),
        (Cell(S.IN_PROGRESS, 2), Cell(S.IN_PROGRESS, 2), Cell(S.NOT_PASSED, 2)),
        (Cell(S.LOCKED), Cell(S.LOCKED), Cell(S.AVAILABLE)),
    ],
)
def test_bo_qua_bat_dau_bo_do_mo_khoa_khong_lam_lech_thong_ke(before, during, after):
    """Kiểm tra số liệu thật của chuyển trạng thái bị skip, kể cả phiên legacy bỏ dở."""
    baseline = [Cell(S.MASTERED, 1)] * 3 + [Cell(S.NOT_PASSED, 1)] * 2
    stats = [aggregate([*baseline, cell], enrolled=30, rule=ColorRule()) for cell in (before, during, after)]
    assert stats[0] == stats[1] == stats[2]


@pytest.mark.parametrize(
    ("attempted", "passed", "color"),
    [
        (4, 4, HeatColor.GREY),
        (5, 4, HeatColor.GREEN),  # 80%
        (10, 7, HeatColor.GREEN),  # 70% đúng biên
        (1000, 699, HeatColor.YELLOW),  # 69,9%
        (5, 2, HeatColor.YELLOW),  # 40% đúng biên
        (1000, 399, HeatColor.RED),  # 39,9%
        (0, 0, HeatColor.GREY),
    ],
)
def test_classify_bien_nguong(attempted, passed, color):
    assert classify(attempted, passed, ColorRule())[0] == color


def test_gv_cau_hinh_nguong_va_co_mau():
    """FR-HM-08 (C2-17 sẽ có màn cấu hình): ngưỡng đọc từ class_sections.color_thresholds, min_sample."""
    rule = ColorRule.from_class({"green": 0.8, "yellow": 0.5}, 10)
    assert classify(9, 9, rule)[0] == HeatColor.GREY
    assert classify(10, 7, rule)[0] == HeatColor.YELLOW
    assert classify(10, 8, rule)[0] == HeatColor.GREEN
    assert classify(10, 4, rule)[0] == HeatColor.RED
    assert ColorRule.from_class(None, None) == ColorRule()
    assert ColorRule.from_class({"green": 0.9}, 3) == ColorRule(green=0.9, yellow=0.4, min_sample=3)


@pytest.mark.parametrize("kwargs", [{"green": 0.3, "yellow": 0.5}, {"green": 1.2}, {"yellow": -0.1}, {"min_sample": 0}])
def test_cau_hinh_sai_bi_tu_choi(kwargs):
    with pytest.raises(ValueError):
        ColorRule(**kwargs)


def test_khong_co_si_so_khong_chia_cho_0():
    st = aggregate([], enrolled=0, rule=ColorRule())
    assert st.attempted_rate == 0 and st.color == HeatColor.GREY


def test_payload_heatmap_node_kem_key_va_nhan():
    """Hợp đồng cho Thắng (SkillTree `heat` tra theo key) – camelCase, có nhãn chữ."""
    node_id = uuid4()
    st = aggregate(LOP_30_SV["n5_nghen"][0], SI_SO, ColorRule())
    body = node_payload(node_id, "n5_con_tro", st, ColorRule()).model_dump(mode="json", by_alias=True)
    assert body["nodeId"] == str(node_id) and body["nodeKey"] == "n5_con_tro"
    assert body["color"] == "RED" and body["sample"] == "SUFFICIENT" and body["label"].startswith("✗")
    assert (body["enrolledCount"], body["attemptedCount"], body["passedCount"], body["minSample"]) == (30, 9, 2, 5)
    assert body["passRate"] == pytest.approx(2 / 9) and body["attemptedRate"] == pytest.approx(0.3)


# --- Hàng đợi aggregation nghe mastery.changed --------------------------------------------------------


def _event(reason: MasteryChangeReason | None, old=S.AVAILABLE, new=S.MASTERED) -> MasteryChanged:
    return MasteryChanged(
        class_id=uuid4(), student_id=uuid4(), node_id=uuid4(), old_state=old, new_state=new, reason=reason
    )


@pytest.mark.parametrize(
    "reason",
    [
        MasteryChangeReason.SESSION_PASSED,
        MasteryChangeReason.SESSION_FAILED,
        MasteryChangeReason.PUBLISH_INIT,
        MasteryChangeReason.PUBLISH_MIGRATE,
        None,
    ],
)
def test_mastery_changed_day_vao_hang_doi(reason):
    bus, queued = InMemoryEventBus(), []
    register_handlers(bus, enqueue=lambda c, n: queued.append((c, n)))
    ev = _event(reason)
    bus.publish(TOPIC_MASTERY_CHANGED, ev)
    assert queued == [(ev.class_id, ev.node_id)]


@pytest.mark.parametrize(
    "reason",
    [MasteryChangeReason.SESSION_STARTED, MasteryChangeReason.SESSION_ABANDONED, MasteryChangeReason.UNLOCKED],
)
def test_doi_trang_thai_khong_doi_so_lieu_thi_bo_qua(reason):
    """Bắt đầu / bỏ dở phiên, mở khóa: số đã thử và số Đạt không đổi ⇒ không tính lại."""
    bus, queued = InMemoryEventBus(), []
    register_handlers(bus, enqueue=lambda c, n: queued.append((c, n)))
    bus.publish(TOPIC_MASTERY_CHANGED, _event(reason))
    assert queued == []


def test_broker_rot_chi_ghi_log_cho_doi_soat(caplog):
    """Redis rớt khi đẩy việc: không làm hỏng bên phát, log có lớp + nút để đối soát."""
    from kombu.exceptions import OperationalError

    def hong(c, n):
        raise OperationalError("broker rớt")

    bus = InMemoryEventBus()
    register_handlers(bus, enqueue=hong)
    ev = _event(MasteryChangeReason.SESSION_PASSED)
    bus.publish(TOPIC_MASTERY_CHANGED, ev)
    assert str(ev.class_id) in caplog.text and "đối soát" in caplog.text


# --- Task Celery (gọi trực tiếp, không cần broker) ----------------------------------------------------


def test_task_recompute_node_commit_va_dong_phien(monkeypatch):
    from app.services.heatmap import HeatmapService
    from app.workers import aggregation

    db = Mock()
    monkeypatch.setattr(aggregation, "_session", lambda: db)
    monkeypatch.setattr(HeatmapService, "recompute", Mock(return_value=None))
    assert aggregation.recompute_node(str(uuid4()), str(uuid4())) is None
    db.commit.assert_called_once()
    db.close.assert_called_once()


def test_task_loi_thi_rollback(monkeypatch):
    from app.services.heatmap import HeatmapService
    from app.workers import aggregation

    db = Mock()
    monkeypatch.setattr(aggregation, "_session", lambda: db)
    monkeypatch.setattr(HeatmapService, "recompute_class", Mock(side_effect=RuntimeError("hỏng")))
    with pytest.raises(RuntimeError):
        aggregation.recompute_class(str(uuid4()))
    db.rollback.assert_called_once()
    db.close.assert_called_once()
    db.commit.assert_not_called()


# --- C2-13: phát realtime -----------------------------------------------------------------------------


@pytest.mark.parametrize("reason", [MasteryChangeReason.SESSION_STARTED, MasteryChangeReason.SESSION_PASSED])
def test_moi_mastery_changed_deu_phat_heatmap_cell(reason):
    """Kể cả bắt đầu phiên (không tính lại số liệu) lưới vẫn hiện ô "đang giảng"."""
    bus, cells = InMemoryEventBus(), []
    register_handlers(bus, enqueue=lambda c, n: None, cell=cells.append)
    ev = _event(reason)
    bus.publish(TOPIC_MASTERY_CHANGED, ev)
    assert [c.student_id for c in cells] == [ev.student_id]


def test_task_phat_node_va_alert_sau_commit(monkeypatch):
    from app.services import heatmap as hm
    from app.workers import aggregation

    order: list[str] = []
    db = Mock()
    db.commit.side_effect = lambda: order.append("commit")
    node = node_payload(uuid4(), "n1", aggregate([], 0, ColorRule()), ColorRule())
    monkeypatch.setattr(aggregation, "_session", lambda: db)
    monkeypatch.setattr(hm.HeatmapService, "recompute", Mock(return_value=node))
    monkeypatch.setattr(hm.HeatmapService, "trace_root_causes", Mock(return_value=["alert"]))
    monkeypatch.setattr(hm, "push_updates", lambda c, n, a: order.append(("push", n, a)))
    aggregation.recompute_node(str(uuid4()), str(uuid4()))
    assert order == ["commit", ("push", [node], ["alert"])]


def test_task_loi_thi_khong_phat(monkeypatch):
    from app.services import heatmap as hm
    from app.workers import aggregation

    pushed = []
    monkeypatch.setattr(aggregation, "_session", lambda: Mock())
    monkeypatch.setattr(hm.HeatmapService, "recompute", Mock(side_effect=RuntimeError("hỏng")))
    monkeypatch.setattr(hm, "push_updates", lambda *a: pushed.append(a))
    with pytest.raises(RuntimeError):
        aggregation.recompute_node(str(uuid4()), str(uuid4()))
    assert pushed == []


def test_redis_rot_khi_phat_chi_ghi_log(monkeypatch, caplog):
    from redis.exceptions import ConnectionError as RedisConnectionError

    from app.realtime import gateway
    from app.services import heatmap as hm

    def hong(*a):
        raise RedisConnectionError("rớt")

    monkeypatch.setattr(gateway, "broadcast", hong)
    cid = uuid4()
    hm.push_updates(cid, [node_payload(uuid4(), "n1", aggregate([], 0, ColorRule()), ColorRule())], [])
    assert str(cid) in caplog.text


def test_heatmap_service_khong_truy_van_thang_bang_lop_cay():
    """AGENTS.md: không truy vấn thẳng bảng phần khác – lớp qua ClassService, cây qua SkillTreeService."""
    import inspect

    from app.services import heatmap as mod

    src = inspect.getsource(mod)
    assert "ClassSection" not in src
    assert "from app.models import tree" not in src


def test_mastery_columns_khong_truy_van_thang_bang_cay():
    import inspect

    from app.services.mastery import MasteryService

    src = inspect.getsource(MasteryService.columns)
    assert "orm." not in src and "ClassSection" not in src
