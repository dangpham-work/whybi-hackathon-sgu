"""RootCauseAnalyzer – truy vết điểm nghẽn gốc (mục 6.5.3, Hình 6.10). Chủ: Long (C2-12).

Với nút đỏ Y, F = SV đã thử Y nhưng Chưa đạt. Với mỗi tổ tiên X (độ sâu ≤ D=3):
  r(X|Y) = |{s ∈ F : s chưa Đạt X}| / |F|;  nếu r ≥ θ (0,6): score = r × (1 + 0,1 × khoảng cách(X, Y))
Chọn X có score lớn nhất; không có ⇒ Y tự là điểm nghẽn.
Ví dụ kiểm thử (Hình 6.9): Y=N6, |F|=9, r(N5|N6)=7/9 ⇒ gốc là N5 Con trỏ.
"""

from dataclasses import dataclass

import networkx as nx


@dataclass
class RootCause:
    node_key: str
    score: float
    conditional_fail_rate: float


def analyze(
    g: nx.DiGraph,
    y: str,
    failed_students: set[str],
    not_mastered: dict[str, set[str]],  # node_key → tập SV chưa Đạt nút đó
    theta: float = 0.6,
    max_depth: int = 3,
    min_sample: int = 5,
) -> RootCause | None:
    raise NotImplementedError("C2-12")
