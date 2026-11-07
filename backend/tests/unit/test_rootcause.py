"""C2-12 – Xong khi: ví dụ ở mục 6.5 (Hình 6.9) cho đúng nút gốc. Hàm thuần, không cần CSDL.

Cây Hình 6.9 (lớp 42 SV): N1→N2, N1→N3, N1→N5, N3→N4, N3→N5, N5→N6, N6→N7, N2→N8, N7→N8.
Truy vết cho Y = N6 (đỏ, 3/12 Đạt ⇒ |F| = 9): r(N5|N6) = 7/9, r(N3|N6) = 1/9, r(N1|N6) = 0 ⇒ gốc là N5 Con trỏ.
"""

from unittest.mock import Mock
from uuid import uuid4

import networkx as nx
import pytest

from app.algorithms.rootcause import RootCause, alert_message, analyze, ancestors_within, trace_class
from app.models.enums import HeatColor

EDGES_6_9 = [
    ("N1", "N2"),
    ("N1", "N3"),
    ("N1", "N5"),
    ("N3", "N4"),
    ("N3", "N5"),
    ("N5", "N6"),
    ("N6", "N7"),
    ("N2", "N8"),
    ("N7", "N8"),
]


def cay_6_9() -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_edges_from(EDGES_6_9)
    return g


def sv(*idx: int) -> set[str]:
    return {f"s{i:02d}" for i in idx}


# F của N6: 9 SV đã thử N6 nhưng Chưa đạt (s01…s09)
F_N6 = sv(*range(1, 10))
# Trong F: 7 SV chưa Đạt N5 (s01…s07), 1 SV chưa Đạt N3 (s08), không ai chưa Đạt N1
NOT_MASTERED_6_9 = {
    "N1": set(),
    "N3": sv(8),
    "N5": sv(*range(1, 8)) | sv(*range(20, 37)),  # thêm SV ngoài F – không được tính vào r(N5|N6)
}


def test_vi_du_hinh_6_9_goc_cua_n6_la_n5():
    rc = analyze(cay_6_9(), "N6", F_N6, NOT_MASTERED_6_9)
    assert isinstance(rc, RootCause)
    assert rc.node_key == "N5" and not rc.is_self
    assert rc.conditional_fail_rate == pytest.approx(7 / 9)  # 0,78 ≥ θ = 0,6
    assert rc.distance == 1
    assert rc.score == pytest.approx(7 / 9 * 1.1)
    assert rc.failed_count == 9
    assert rc.ratios == pytest.approx({"N5": 7 / 9, "N3": 1 / 9, "N1": 0.0})


def test_to_tien_bfs_nguoc_lay_khoang_cach_ngan_nhat():
    # N1→N5→N6 dài 2 (ngắn hơn N1→N3→N5→N6)
    assert ancestors_within(cay_6_9(), "N6", 3) == {"N5": 1, "N3": 2, "N1": 2}
    assert ancestors_within(cay_6_9(), "N8", 2) == {"N2": 1, "N7": 1, "N1": 2, "N6": 2}
    assert ancestors_within(cay_6_9(), "N1", 3) == {}


def test_uu_tien_ung_vien_xa_hon_khi_diem_cao_hon():
    # r(N5|N6)=0,7 ⇒ 0,77; r(N3|N6)=0,7 ⇒ 0,7 × 1,2 = 0,84 ⇒ N3 (lỗ hổng nền tảng hơn)
    f = sv(*range(1, 11))
    nm = {"N5": sv(*range(1, 8)), "N3": sv(*range(4, 11)), "N1": set()}
    rc = analyze(cay_6_9(), "N6", f, nm)
    assert rc.node_key == "N3" and rc.distance == 2
    assert rc.score == pytest.approx(0.7 * 1.2)


def test_ung_vien_gan_thang_khi_ti_le_vuot_troi():
    # r(N5)=1,0 ⇒ 1,1; r(N3)=0,6 ⇒ 0,72 ⇒ N5
    f = sv(*range(1, 11))
    nm = {"N5": f, "N3": sv(*range(1, 7)), "N1": set()}
    assert analyze(cay_6_9(), "N6", f, nm).node_key == "N5"


def test_bien_theta_dung_0_6_la_ung_vien():
    f = sv(1, 2, 3, 4, 5)
    nm = {"N5": sv(1, 2, 3)}  # 3/5 = 0,6 đúng ngưỡng
    rc = analyze(cay_6_9(), "N6", f, nm)
    assert rc.node_key == "N5" and rc.conditional_fail_rate == pytest.approx(0.6)


def test_duoi_theta_thi_y_tu_la_diem_nghen():
    f = sv(*range(1, 11))
    nm = {"N5": sv(1, 2, 3, 4, 5), "N3": sv(1), "N1": set()}  # 0,5 < 0,6
    rc = analyze(cay_6_9(), "N6", f, nm)
    assert rc.node_key == "N6" and rc.is_self and rc.distance == 0


def test_khong_co_tien_quyet_thi_tu_la_diem_nghen():
    rc = analyze(cay_6_9(), "N1", sv(*range(1, 8)), {})
    assert rc.node_key == "N1" and rc.is_self and rc.ratios == {}


def test_co_mau_nho_khong_ket_luan():
    # |F| = 4 < cỡ mẫu tối thiểu 5 ⇒ không kết luận (Hình 6.10)
    assert analyze(cay_6_9(), "N6", sv(1, 2, 3, 4), {"N5": sv(1, 2, 3, 4)}) is None
    assert analyze(cay_6_9(), "N6", set(), {}) is None
    # GV hạ cỡ mẫu xuống 4 thì kết luận được
    assert analyze(cay_6_9(), "N6", sv(1, 2, 3, 4), {"N5": sv(1, 2, 3, 4)}, min_sample=4).node_key == "N5"


def test_gioi_han_do_sau_d():
    # chuỗi A→B→C→D→E: với D=3, A (khoảng cách 4) không được xét
    g = nx.DiGraph([("A", "B"), ("B", "C"), ("C", "D"), ("D", "E")])
    f = sv(*range(1, 6))
    rc = analyze(g, "E", f, {"A": f})
    assert rc.is_self and "A" not in rc.ratios
    assert analyze(g, "E", f, {"A": f}, max_depth=4).node_key == "A"


def test_nhieu_nghen_hoa_diem_chon_xa_hon_roi_theo_key():
    # N3, N1 cùng khoảng cách 2 và cùng r ⇒ cùng điểm: chọn ổn định theo key (N1 < N3)
    f = sv(*range(1, 6))
    rc = analyze(cay_6_9(), "N6", f, {"N3": f, "N1": f})
    assert rc.node_key == "N1"


def test_hoa_diem_khac_khoang_cach_khong_lech_do_so_thuc():
    # 12/12 × 1,1 = 11/12 × 1,2 = 1,1: phải chọn tổ tiên xa hơn.
    # float cho 11/12 × 1,2 = 1,0999999999999999, làm mất nhánh hòa điểm.
    g = nx.DiGraph([("far", "near"), ("near", "y")])
    f = sv(*range(1, 13))
    rc = analyze(g, "y", f, {"near": f, "far": sv(*range(1, 12))})
    assert rc.node_key == "far" and rc.distance == 2
    assert rc.score == pytest.approx(1.1)


def test_nut_khong_co_trong_cay_bi_tu_choi():
    with pytest.raises(ValueError):
        analyze(cay_6_9(), "N99", sv(*range(1, 6)), {})


@pytest.mark.parametrize("kwargs", [{"theta": 0}, {"theta": 1.5}, {"max_depth": 0}, {"min_sample": 0}])
def test_tham_so_sai_bi_tu_choi(kwargs):
    with pytest.raises(ValueError):
        analyze(cay_6_9(), "N6", F_N6, NOT_MASTERED_6_9, **kwargs)


def test_truy_vet_ca_lop_chi_xet_nut_do():
    colors = {
        "N1": HeatColor.GREEN,
        "N2": HeatColor.GREEN,
        "N3": HeatColor.GREEN,
        "N4": HeatColor.GREY,
        "N5": HeatColor.RED,
        "N6": HeatColor.RED,
        "N7": HeatColor.YELLOW,
        "N8": HeatColor.YELLOW,
    }
    # N5: 25 thử, 8 Đạt ⇒ |F| = 17; trong F gần như ai cũng đã Đạt N1, N3 ⇒ N5 tự là điểm nghẽn
    failed = {"N5": sv(*range(20, 37)), "N6": F_N6, "N7": sv(40, 41)}
    out = trace_class(cay_6_9(), colors, failed, NOT_MASTERED_6_9)
    assert set(out) == {"N5", "N6"}  # N7 vàng: không truy vết
    assert out["N6"].node_key == "N5" and not out["N6"].is_self
    assert out["N5"].node_key == "N5" and out["N5"].is_self


def test_nut_do_chua_du_mau_truot_bi_bo_qua():
    out = trace_class(cay_6_9(), {"N6": HeatColor.RED}, {"N6": sv(1, 2)}, {"N5": sv(1, 2)})
    assert out == {}


def test_thong_diep_canh_bao():
    assert alert_message("N5", "Con trỏ") == "Nên giảng lại N5 Con trỏ"
    assert alert_message(None, "Con trỏ") == "Nên giảng lại Con trỏ"


# --- Hàng đợi aggregation: tính lại xong thì truy vết gốc trong cùng giao dịch (không cần broker / CSDL) -----


def test_task_recompute_node_truy_vet_goc_truoc_commit(monkeypatch):
    from app.services.heatmap import HeatmapService
    from app.workers import aggregation

    db, calls = Mock(), []
    db.commit.side_effect = lambda: calls.append("commit")
    node = Mock()
    node.model_dump.return_value = {"nodeId": "x"}
    monkeypatch.setattr(aggregation, "_session", lambda: db)
    monkeypatch.setattr(HeatmapService, "recompute", Mock(return_value=node))
    monkeypatch.setattr(HeatmapService, "trace_root_causes", Mock(side_effect=lambda *_: calls.append("trace") or []))
    monkeypatch.setattr("app.services.heatmap.push_updates", lambda *_: calls.append("push"))  # C2-13
    assert aggregation.recompute_node(str(uuid4()), str(uuid4())) == {"nodeId": "x"}
    assert calls == ["trace", "commit", "push"]


def test_task_recompute_node_bo_qua_khi_nut_khong_thuoc_ban_phat_hanh(monkeypatch):
    from app.services.heatmap import HeatmapService
    from app.workers import aggregation

    monkeypatch.setattr(aggregation, "_session", lambda: Mock())
    monkeypatch.setattr(HeatmapService, "recompute", Mock(return_value=None))
    trace = Mock()
    monkeypatch.setattr(HeatmapService, "trace_root_causes", trace)
    assert aggregation.recompute_node(str(uuid4()), str(uuid4())) is None
    trace.assert_not_called()


def test_task_recompute_class_truy_vet_goc(monkeypatch):
    from app.services.heatmap import HeatmapService
    from app.workers import aggregation

    monkeypatch.setattr(aggregation, "_session", lambda: Mock())
    monkeypatch.setattr(HeatmapService, "recompute_class", Mock(return_value=[Mock(), Mock()]))
    trace = Mock(return_value=[])
    monkeypatch.setattr(HeatmapService, "trace_root_causes", trace)
    monkeypatch.setattr("app.services.heatmap.push_updates", Mock())  # C2-13: phát sau commit
    assert aggregation.recompute_class(str(uuid4())) == 2
    trace.assert_called_once()
