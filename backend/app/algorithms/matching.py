"""Ghép cặp bù trừ (mục 6.6, Hình 6.12). Chủ: Long (C2-14, C2-15).

p(n) = 1 + α·(1 − tỉ lệ Đạt của n)
w(a,b) = min( Σp(n), n ∈ Đạt(a) ∩ Biên(b) ;  Σp(n), n ∈ Đạt(b) ∩ Biên(a) )   – bắt buộc hai chiều (BR-08)
Giải bằng nx.max_weight_matching (Blossom, O(V³)); dự phòng: tham lam theo trọng số giảm dần.
SV lẻ: ghép một chiều với mentor đã Đạt nút Biên có p cao nhất, hoặc vào hàng chờ.
Ví dụ kiểm thử (Hình 6.11): An ↔ Châu, w = 1,33 (An dạy N5, Châu dạy N4); Hà một chiều với Dũng.
"""

from dataclasses import dataclass


@dataclass
class PairResult:
    a: str
    b: str
    weight: float
    a_teaches: list[str]  # ≤ m nút có p cao nhất
    b_teaches: list[str]


def node_priority(pass_rate: dict[str, float], alpha: float = 1.0) -> dict[str, float]:
    raise NotImplementedError("C2-14")


def complementarity(
    a: str, b: str, mastered: dict[str, set[str]], frontier: dict[str, set[str]], p: dict[str, float]
) -> float:
    raise NotImplementedError("C2-14")


def run_round(
    students: list[str],
    mastered: dict[str, set[str]],
    frontier: dict[str, set[str]],
    pass_rate: dict[str, float],
    recent_pairs: set[frozenset[str]],
    alpha: float = 1.0,
    m: int = 2,
) -> tuple[list[PairResult], list[str]]:
    """Trả (các cặp, SV chưa ghép). Mã giả ở mục 6.6.5. < 2 giây cho lớp 100 SV (UC15)."""
    raise NotImplementedError("C2-14")
