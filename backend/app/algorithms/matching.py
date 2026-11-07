"""Ghép cặp bù trừ (mục 6.6, Hình 6.12). Chủ: Long (C2-14, C2-15).

p(n) = 1 + α·(1 − tỉ lệ Đạt của n)
w(a,b) = min( Σp(n), n ∈ Đạt(a) ∩ Biên(b) ;  Σp(n), n ∈ Đạt(b) ∩ Biên(a) )   – bắt buộc hai chiều (BR-08)
Giải bằng nx.max_weight_matching (Blossom, O(V³)).
SV lẻ: ghép một chiều với mentor (cũng chưa có cặp) đã Đạt nút Biên của bạn đó, tổng p cao nhất; không có thì
vào hàng chờ.
Ví dụ kiểm thử (Hình 6.11): An ↔ Châu, w = 1,33 (An dạy N5, Châu dạy N4); Hà một chiều với Dũng; Khang chờ.

Hàm thuần, không I/O: định danh SV và nút là chuỗi bất kỳ (service truyền str(uuid) và key nút).
"""

from collections.abc import Iterable
from dataclasses import dataclass
from itertools import combinations

import networkx as nx


@dataclass
class PairResult:
    a: str
    b: str
    weight: float
    a_teaches: list[str]  # ≤ m nút có p cao nhất
    b_teaches: list[str]
    one_way: bool = False  # True: a là mentor, b chỉ học (b_teaches rỗng)


def node_priority(pass_rate: dict[str, float], alpha: float = 1.0) -> dict[str, float]:
    """p(n) = 1 + α·(1 − tỉ lệ Đạt) – nút càng là điểm nghẽn càng được ưu tiên."""
    return {n: 1 + alpha * (1 - r) for n, r in pass_rate.items()}


def _sum(nodes: Iterable[str], p: dict[str, float]) -> float:
    return sum(p.get(n, 1.0) for n in nodes)


def _top(nodes: Iterable[str], p: dict[str, float], m: int) -> list[str]:
    """m nút có p cao nhất; hòa thì theo tên nút cho ổn định."""
    return sorted(nodes, key=lambda n: (-p.get(n, 1.0), n))[:m]


def complementarity(
    a: str, b: str, mastered: dict[str, set[str]], frontier: dict[str, set[str]], p: dict[str, float]
) -> float:
    """w(a, b) theo 6.6.2; = 0 khi một bên không có gì để dạy bên kia."""
    t_ab = mastered.get(a, set()) & frontier.get(b, set())
    t_ba = mastered.get(b, set()) & frontier.get(a, set())
    if not t_ab or not t_ba:
        return 0.0
    return min(_sum(t_ab, p), _sum(t_ba, p))


def run_round(
    students: list[str],
    mastered: dict[str, set[str]],
    frontier: dict[str, set[str]],
    pass_rate: dict[str, float],
    recent_pairs: set[frozenset[str]],
    alpha: float = 1.0,
    m: int = 2,
) -> tuple[list[PairResult], list[str]]:
    """Trả (các cặp, SV chưa ghép – hàng chờ). Mã giả ở mục 6.6.5. < 2 giây cho lớp 100 SV (UC15).

    Kết quả xác định: cặp hai chiều trước (sắp theo trọng số giảm dần), rồi cặp một chiều."""
    p = node_priority(pass_rate, alpha)
    g = nx.Graph()
    g.add_nodes_from(students)
    for a, b in combinations(students, 2):
        if frozenset((a, b)) in recent_pairs:
            continue
        w = complementarity(a, b, mastered, frontier, p)
        if w > 0:
            g.add_edge(a, b, weight=w)

    pairs: list[PairResult] = []
    for u, v in nx.max_weight_matching(g, maxcardinality=False):
        a, b = sorted((u, v))
        pairs.append(
            PairResult(
                a=a,
                b=b,
                weight=g.edges[a, b]["weight"],
                a_teaches=_top(mastered[a] & frontier[b], p, m),
                b_teaches=_top(mastered[b] & frontier[a], p, m),
            )
        )
    pairs.sort(key=lambda x: (-x.weight, x.a, x.b))

    used = {s for x in pairs for s in (x.a, x.b)}
    rest = [s for s in students if s not in used]

    # SV lẻ / không có cặp hai chiều: ghép một chiều (mentor → người học), tham lam theo tổng p giảm dần.
    options: list[tuple[float, str, str, list[str]]] = []
    for learner in rest:
        for mentor in rest:
            if mentor == learner or frozenset((mentor, learner)) in recent_pairs:
                continue
            teach = _top(mastered.get(mentor, set()) & frontier.get(learner, set()), p, m)
            if teach:
                options.append((_sum(teach, p), mentor, learner, teach))
    options.sort(key=lambda o: (-o[0], o[2], o[1]))
    for score, mentor, learner, teach in options:
        if mentor in used or learner in used:
            continue
        pairs.append(PairResult(a=mentor, b=learner, weight=score, a_teaches=teach, b_teaches=[], one_way=True))
        used |= {mentor, learner}

    return pairs, [s for s in students if s not in used]
