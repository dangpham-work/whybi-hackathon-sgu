"""KT-11 (#50) – FR-PM-03: ghép cặp bù trừ (C2-14, mục 6.6) luôn đúng ràng buộc trên lớp ngẫu nhiên.

Bổ sung cho test của Long (tests/unit/test_matching_algo.py – ví dụ 6.6.4, 100 SV < 2 giây). Ở đây sinh 300 lớp
ngẫu nhiên (hạt giống cố định) trên cây mẫu `seed/tree_ctdl_gt.json`: tập Đạt luôn "đóng" theo tiên quyết (BR-02),
Biên = nút chưa Đạt mà mọi tiên quyết đã Đạt (6.6.2). Mỗi kết quả `run_round` phải thỏa:

1. Không SV nào ở hai cặp; mọi SV đầu vào hoặc có cặp hoặc nằm trong hàng chờ.
2. Cặp hai chiều: mỗi bên dạy ≥ 1 và ≤ m nút, nút dạy ∈ Đạt(người dạy) ∩ Biên(người học), là m nút p cao nhất;
   trọng số = min hai chiều (BR-08).
3. Cặp một chiều chỉ dùng cho SV không có cặp hai chiều; người học không dạy gì; người dạy có nút để dạy.
4. Cặp vừa ghép trong 14 ngày (recent_pairs) không bao giờ xuất hiện lại.
5. Tối ưu: tổng trọng số hai chiều = cực đại tìm vét cạn (lớp ≤ 8 SV); không còn cạnh dương nào giữa hai SV
   chưa ghép hai chiều; hàng chờ không còn cặp mentor → người học nào khả thi.

Hàm thuần – chạy không cần Docker.
"""

import random
from itertools import combinations

import networkx as nx
import pytest

from app.algorithms.matching import complementarity, node_priority, run_round
from tests.unit.test_tree_edit_db import SEED

M = 2


@pytest.fixture(scope="module")
def cay() -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_nodes_from(n["key"] for n in SEED["nodes"])
    g.add_edges_from((e["fromKey"], e["toKey"]) for e in SEED["edges"])
    return g


def tap_dat_ngau_nhien(g: nx.DiGraph, rng: random.Random) -> set[str]:
    """Đi theo thứ tự tô-pô; nút chỉ có thể Đạt khi mọi tiên quyết đã Đạt."""
    mastered: set[str] = set()
    p = rng.choice([0.3, 0.6, 0.9])
    for n in nx.topological_sort(g):
        if all(pre in mastered for pre in g.predecessors(n)) and rng.random() < p:
            mastered.add(n)
    return mastered


def bien(g: nx.DiGraph, mastered: set[str]) -> set[str]:
    return {n for n in g if n not in mastered and all(pre in mastered for pre in g.predecessors(n))}


def lop_ngau_nhien(g, rng, size):
    students = [f"s{i:02d}" for i in range(size)]
    mastered = {s: tap_dat_ngau_nhien(g, rng) for s in students}
    frontier = {s: bien(g, mastered[s]) for s in students}
    pass_rate = {n: sum(n in mastered[s] for s in students) / size for n in g}
    recent = {frozenset(p) for p in combinations(students, 2) if rng.random() < 0.1}
    priority = rng.choice([None, None, rng.choice(sorted(g))])
    return students, mastered, frontier, pass_rate, recent, priority


def cuc_dai_vet_can(students, weight) -> float:
    """Tổng trọng số lớn nhất của một tập cặp không trùng đỉnh – vét cạn đệ quy (chỉ dùng cho lớp nhỏ)."""

    def best(rest: tuple[str, ...]) -> float:
        if len(rest) < 2:
            return 0.0
        first, others = rest[0], rest[1:]
        value = best(others)  # `first` không ghép
        for j, other in enumerate(others):
            w = weight(first, other)
            if w > 0:
                value = max(value, w + best(others[:j] + others[j + 1 :]))
        return value

    return best(tuple(students))


def kiem_rang_buoc(students, mastered, frontier, pass_rate, recent, priority, pairs, waiting):
    p = node_priority(pass_rate, 1.0, priority)

    def w(a, b):
        return 0.0 if frozenset((a, b)) in recent else complementarity(a, b, mastered, frontier, p)

    seen = [s for x in pairs for s in (x.a, x.b)]
    assert len(seen) == len(set(seen)), "một SV nằm trong hai cặp"
    assert set(seen) | set(waiting) == set(students) and not set(seen) & set(waiting)

    def top(nodes):
        return sorted(nodes, key=lambda n: (-p.get(n, 1.0), n))[:M]

    two_way = [x for x in pairs if not x.one_way]
    for x in pairs:
        assert frozenset((x.a, x.b)) not in recent, f"ghép lại cặp vừa ghép {x.a}–{x.b}"
        assert 1 <= len(x.a_teaches) <= M
        assert set(x.a_teaches) <= mastered[x.a] & frontier[x.b]
        assert x.a_teaches == top(mastered[x.a] & frontier[x.b])
        if x.one_way:
            assert x.b_teaches == []
        else:
            assert 1 <= len(x.b_teaches) <= M
            assert set(x.b_teaches) <= mastered[x.b] & frontier[x.a]
            assert x.b_teaches == top(mastered[x.b] & frontier[x.a])
            assert x.weight == pytest.approx(w(x.a, x.b)) and x.weight > 0

    # Cực đại: không còn cạnh dương giữa hai SV ngoài cặp hai chiều (nếu có, thêm vào sẽ tăng tổng).
    free = [s for s in students if s not in {t for x in two_way for t in (x.a, x.b)}]
    assert all(w(a, b) == 0 for a, b in combinations(free, 2))
    # Hàng chờ: không còn mentor nào trong hàng chờ dạy được bạn khác trong hàng chờ.
    for a in waiting:
        for b in waiting:
            if a != b and frozenset((a, b)) not in recent:
                assert not mastered[a] & frontier[b], f"{a} dạy được {b} mà cả hai vẫn chờ"
    return w, sum(x.weight for x in two_way)


@pytest.mark.parametrize("seed", range(300))
def test_ghep_cap_dung_rang_buoc_tren_lop_ngau_nhien(cay, seed):
    rng = random.Random(1100 + seed)
    size = rng.randint(2, 8)
    students, mastered, frontier, pass_rate, recent, priority = lop_ngau_nhien(cay, rng, size)
    pairs, waiting = run_round(students, mastered, frontier, pass_rate, recent, m=M, priority_node=priority)
    w, total = kiem_rang_buoc(students, mastered, frontier, pass_rate, recent, priority, pairs, waiting)
    assert total == pytest.approx(cuc_dai_vet_can(students, w)), "tổng trọng số hai chiều chưa cực đại"


def test_lop_30_sv_dung_rang_buoc(cay):
    rng = random.Random(2026)
    students, mastered, frontier, pass_rate, recent, priority = lop_ngau_nhien(cay, rng, 30)
    pairs, waiting = run_round(students, mastered, frontier, pass_rate, recent, m=M, priority_node=priority)
    kiem_rang_buoc(students, mastered, frontier, pass_rate, recent, priority, pairs, waiting)
    assert pairs, "lớp 30 SV ngẫu nhiên phải ghép được ít nhất một cặp"


def test_sv_da_dat_het_hoac_chua_dat_gi_vao_hang_cho(cay):
    """Khang (6.6.4): không có nút Biên chung với ai ⇒ chờ vòng sau, không bị ép ghép."""
    everything = set(cay)
    students = ["gioi", "moi"]
    mastered = {"gioi": everything, "moi": everything}
    frontier = {s: bien(cay, mastered[s]) for s in students}
    pairs, waiting = run_round(students, mastered, frontier, dict.fromkeys(cay, 0.5), set())
    assert pairs == [] and waiting == students
