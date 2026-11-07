"""KT-11 (#50) – FR-HM-05: truy vết điểm nghẽn gốc (C2-12, mục 6.5.3) trên cây NHIỀU TẦNG.

Bổ sung cho test của Long (tests/unit/test_rootcause*.py – ví dụ Hình 6.9, đồ thị nhỏ viết tay). Ở đây dùng
đúng cây mẫu `seed/tree_ctdl_gt.json` (chuỗi sâu N1 → N3 → N5 → N6 → N7 → N9 → N10 → N11, có kim cương
N3 → N4 → N9) để kiểm giới hạn độ sâu D, khoảng cách ngắn nhất, ưu tiên nút xa và lan truyền về một gốc chung.

Phần hàm thuần chạy không cần Docker; test cuối cần `TEST_DATABASE_URL` (đi qua MasteryService + HeatmapService).
"""

import networkx as nx
import pytest

from app.algorithms.rootcause import alert_message, analyze, ancestors_within, trace_class
from app.models.enums import HeatColor, MasteryState
from app.services.heatmap import HeatmapService
from tests.unit import test_heatmap_db as _c211
from tests.unit.test_heatmap_db import hoc
from tests.unit.test_tree_edit_db import DB_URL, SEED

world = _c211.world
lop30 = _c211.lop30

N1, N3, N4, N5, N6, N7 = "n1_bien_bo_nho", "n3_ham_tham_so", "n4_de_quy", "n5_con_tro", "n6_cap_phat_dong", "n7_dslk"
N9, N10, N11 = "n9_cay_nhi_phan", "n10_bst", "n11_avl"

F = {f"sv{i}" for i in range(10)}  # 10 SV đã thử Y nhưng Chưa đạt
BAY = {f"sv{i}" for i in range(7)}  # 7/10 = 0,7 ≥ θ


@pytest.fixture(scope="module")
def cay() -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_nodes_from(n["key"] for n in SEED["nodes"])
    g.add_edges_from((e["fromKey"], e["toKey"]) for e in SEED["edges"])
    assert nx.is_directed_acyclic_graph(g)
    assert nx.dag_longest_path_length(g) == 7  # N1 → … → N11: cây nhiều tầng thật
    return g


def test_khoang_cach_to_tien_la_duong_ngan_nhat_qua_kim_cuong(cay):
    # N3 tới N9 có hai đường: N3→N4→N9 (2 cạnh) và N3→N5→N6→N7→N9 (4 cạnh) ⇒ lấy 2.
    d = ancestors_within(cay, N9, 3)
    assert d == {N7: 1, N4: 1, N6: 2, N3: 2, N5: 3, N1: 3}
    assert "n2_mang" not in d  # N2 không phải tổ tiên của N9


def test_hai_tang_cung_ti_le_thi_chon_tang_xa_hon(cay):
    # Y = N11: r(N10|N11) = r(N9|N11) = 0,7 ⇒ N9 (khoảng cách 2, điểm 0,84) thắng N10 (1, điểm 0,77).
    rc = analyze(cay, N11, F, {N10: BAY, N9: BAY})
    assert (rc.node_key, rc.distance, rc.is_self) == (N9, 2, False)
    assert rc.score == pytest.approx(0.7 * 1.2)
    assert rc.ratios[N10] == pytest.approx(0.7) and rc.ratios[N7] == 0 and rc.ratios[N4] == 0
    assert set(rc.ratios) == {N10, N9, N7, N4}  # chỉ tổ tiên trong độ sâu D = 3


def test_tang_gan_thang_khi_ti_le_vuot_troi(cay):
    # r(N10|N11) = 1,0 ⇒ 1,1 > r(N7|N11) = 0,6 ở khoảng cách 3 ⇒ 0,78.
    rc = analyze(cay, N11, F, {N10: F, N7: {f"sv{i}" for i in range(6)}})
    assert (rc.node_key, rc.distance) == (N10, 1)


def test_to_tien_qua_do_sau_d_bi_bo_qua_tru_khi_tang_d(cay):
    # N6 cách N11 4 cạnh: mặc định D = 3 không xét ⇒ N11 tự là điểm nghẽn; D = 4 thì truy về N6.
    rc = analyze(cay, N11, F, {N6: F})
    assert rc.is_self and rc.node_key == N11 and N6 not in rc.ratios
    rc4 = analyze(cay, N11, F, {N6: F}, max_depth=4)
    assert (rc4.node_key, rc4.distance, rc4.is_self) == (N6, 4, False)
    assert rc4.score == pytest.approx(1.4)


def test_nhieu_nut_do_lan_truyen_ve_mot_goc_chung(cay):
    # Lỗ hổng nền ở N5: SV trượt N6, N7, N9 đều chưa Đạt N5 (N1, N3 đã Đạt) ⇒ cả ba cảnh báo "giảng lại N5".
    failed = {N6: F, N7: F, N9: F}
    colors = {k: HeatColor.GREEN for k in cay} | {N6: HeatColor.RED, N7: HeatColor.RED, N9: HeatColor.RED}
    out = trace_class(cay, colors, failed, {N5: F})
    assert {y: (rc.node_key, rc.distance) for y, rc in out.items()} == {N6: (N5, 1), N7: (N5, 2), N9: (N5, 3)}
    titles = {n["key"]: (n["code"], n["title"]) for n in SEED["nodes"]}
    assert alert_message(*titles[N5]).startswith("Nên giảng lại N5 Con trỏ")


def test_nut_do_thieu_mau_truot_khong_ket_luan_tren_cay_sau(cay):
    colors = {N11: HeatColor.RED, N10: HeatColor.RED}
    out = trace_class(cay, colors, {N11: F, N10: {"sv0", "sv1"}}, {N9: F})
    assert set(out) == {N11}  # N10 chỉ 2 SV trượt < cỡ mẫu 5 ⇒ không kết luận


# ------------------------------------------------------------------ CSDL thật


def phat_hanh_lai(w, key: str):
    """Phát hành bản mới đổi ngưỡng Đạt của `key` ⇒ ô MASTERED của nút đó thành NEEDS_REVERIFY (BR-14)."""
    tree = w.api.post(f"/api/v1/classes/{w.class_id}/tree-versions")
    assert tree.status_code == 201, tree.text
    for node in tree.json()["nodes"]:
        rubric = node["rubric"] | {"approved": True}
        if node["key"] == key:
            rubric["passThreshold"] = 80
        r = w.api.put(f"/api/v1/nodes/{node['id']}/rubric", json=rubric)
        assert r.status_code == 200, r.text
    r = w.api.post(f"/api/v1/tree-versions/{tree.json()['id']}/publish")
    assert r.status_code == 200, r.text
    return {n["key"]: n["id"] for n in r.json()["nodes"]}


@pytest.mark.skipif(not DB_URL, reason="đặt TEST_DATABASE_URL để chạy trên Postgres thật")
def test_csdl_goc_cach_ba_tang_n7_ve_n3(lop30):
    """10 SV học N1→N3→N5→N6; GV đổi rubric N3 (cần xác nhận lại); 8 SV trượt N7, 7 trong số đó trượt luôn
    lượt xác nhận lại N3 ⇒ cảnh báo của N7 chỉ về N3 (cách 3 tầng), không phải N6/N5 kề bên."""
    from uuid import UUID

    w, svc, sv, ids, _ = lop30
    hoc_vien = sv[:10]
    for s in hoc_vien:
        for key in (N1, N3, N5, N6):
            hoc(w, svc, s, ids[key], passed=True)
    ids = {k: UUID(v) for k, v in phat_hanh_lai(w, N3).items()}
    matrix = svc.class_matrix(w.class_id)
    assert all(matrix.cells[N3][s].state == MasteryState.NEEDS_REVERIFY for s in hoc_vien)
    for i, s in enumerate(hoc_vien):
        hoc(w, svc, s, ids[N7], passed=i < 2)  # N7: 2/10 Đạt ⇒ ĐỎ
    truot_n7 = hoc_vien[2:]
    for s in truot_n7[:7]:
        hoc(w, svc, s, ids[N3], passed=False)  # xác nhận lại N3 thất bại
    HeatmapService(w.db).recompute_class(w.class_id)

    alerts = {a.node_key: a for a in HeatmapService(w.db).trace_root_causes(w.class_id)}
    assert N7 in alerts, f"thiếu cảnh báo N7: {sorted(alerts)}"
    a = alerts[N7]
    assert (a.root_cause_node_key, a.distance, a.failed_count, a.is_self) == (N3, 3, 8, False)
    assert a.conditional_fail_rate == pytest.approx(7 / 8)
    assert a.score == pytest.approx(7 / 8 * 1.3)
    title = next(n["title"] for n in SEED["nodes"] if n["key"] == N3)
    assert a.message == alert_message("N3", title)
