"""RootCauseAnalyzer – truy vết điểm nghẽn gốc (mục 6.5.3, Hình 6.10). Chủ: Long (C2-12). Hàm thuần, không I/O.

Với nút đỏ Y, F = SV đã thử Y nhưng Chưa đạt. |F| < cỡ mẫu tối thiểu ⇒ không kết luận (None).
Với mỗi tổ tiên X (BFS ngược, khoảng cách ngắn nhất ≤ D=3):
  r(X|Y) = |{s ∈ F : s chưa Đạt X}| / |F|;  nếu r ≥ θ (0,6): score = r × (1 + 0,1 × khoảng cách(X, Y))
Chọn X có score lớn nhất (hòa điểm: xa Y hơn, rồi theo key cho ổn định); không có ứng viên ⇒ Y tự là điểm nghẽn.
Ví dụ kiểm thử (Hình 6.9): Y=N6, |F|=9, r(N5|N6)=7/9 ⇒ gốc là N5 Con trỏ (tests/unit/test_rootcause.py).

Độ phức tạp (6.5.4): O(|tổ tiên| × |F|) cho một Y.
"""

from collections import deque
from collections.abc import Hashable, Mapping, Set
from dataclasses import dataclass, field
from fractions import Fraction

import networkx as nx

from app.models.enums import HeatColor

DEFAULT_THETA = 0.6
DEFAULT_MAX_DEPTH = 3
DEFAULT_MIN_SAMPLE = 5
DISTANCE_BONUS = 0.1  # score = r × (1 + 0,1 × khoảng cách) – Hình 6.10


@dataclass(frozen=True)
class RootCause:
    """Kết luận truy vết cho một nút đỏ Y."""

    node_key: str  # nút nên giảng lại (= Y khi Y tự là điểm nghẽn)
    score: float  # r × (1 + 0,1 × khoảng cách); Y tự là nghẽn ⇒ 1,0 (r(Y|Y) = 1, khoảng cách 0)
    conditional_fail_rate: float  # r(X|Y)
    distance: int = 0  # khoảng cách X → Y trong DAG; 0 khi Y tự là điểm nghẽn
    failed_count: int = 0  # |F|
    is_self: bool = False
    ratios: Mapping[str, float] = field(default_factory=dict)  # r(X|Y) của mọi tổ tiên đã xét (GV-06 chi tiết)


def ancestors_within(g: nx.DiGraph, y: str, max_depth: int) -> dict[str, int]:
    """Tổ tiên của Y với khoảng cách ngắn nhất (số cạnh) ≤ max_depth – BFS ngược theo cạnh tiên quyết."""
    dist: dict[str, int] = {}
    queue = deque([(y, 0)])
    seen = {y}
    while queue:
        node, d = queue.popleft()
        if d == max_depth:
            continue
        for p in g.predecessors(node):
            if p not in seen:
                seen.add(p)
                dist[p] = d + 1
                queue.append((p, d + 1))
    return dist


def _check_params(theta: float, max_depth: int, min_sample: int) -> None:
    if not 0 < theta <= 1:
        raise ValueError(f"θ phải thuộc (0, 1] (theta={theta})")
    if max_depth < 1:
        raise ValueError(f"độ sâu tối đa phải ≥ 1 (max_depth={max_depth})")
    if min_sample < 1:
        raise ValueError(f"cỡ mẫu tối thiểu phải ≥ 1 (min_sample={min_sample})")


def analyze(
    g: nx.DiGraph,
    y: str,
    failed_students: Set[Hashable],
    not_mastered: Mapping[str, Set[Hashable]],  # node_key → tập SV chưa Đạt nút đó (thiếu key ⇒ coi như rỗng)
    theta: float = DEFAULT_THETA,
    max_depth: int = DEFAULT_MAX_DEPTH,
    min_sample: int = DEFAULT_MIN_SAMPLE,
) -> RootCause | None:
    """Hình 6.10. None = không kết luận (|F| < cỡ mẫu tối thiểu)."""
    _check_params(theta, max_depth, min_sample)
    if y not in g:
        raise ValueError(f"nút {y!r} không có trong cây")
    f = set(failed_students)
    if len(f) < min_sample:
        return None
    theta_q = Fraction(str(theta))  # so ngưỡng bằng phân số đúng: 3/5 = 0,6 là ứng viên
    ratios: dict[str, float] = {}
    best: tuple[Fraction, int, str, Fraction] | None = None  # (score, khoảng cách, key, r)
    for x, d in sorted(ancestors_within(g, y, max_depth).items()):
        r = Fraction(len(f & set(not_mastered.get(x, ()))), len(f))
        ratios[x] = float(r)
        if r < theta_q:
            continue
        score = r * (1 + Fraction(str(DISTANCE_BONUS)) * d)
        # điểm cao hơn thắng; hòa điểm ⇒ xa Y hơn; vẫn hòa ⇒ key nhỏ hơn (duyệt theo key tăng dần, giữ cái đầu)
        if best is None or (score, d) > (best[0], best[1]):
            best = (score, d, x, r)
    if best is None:
        return RootCause(
            node_key=y, score=1.0, conditional_fail_rate=1.0, failed_count=len(f), is_self=True, ratios=ratios
        )
    score, d, x, r = best
    return RootCause(
        node_key=x, score=float(score), conditional_fail_rate=float(r), distance=d, failed_count=len(f), ratios=ratios
    )


def trace_class(
    g: nx.DiGraph,
    colors: Mapping[str, HeatColor],
    failed: Mapping[str, Set[Hashable]],  # node_key → F (SV đã thử nhưng Chưa đạt)
    not_mastered: Mapping[str, Set[Hashable]],
    theta: float = DEFAULT_THETA,
    max_depth: int = DEFAULT_MAX_DEPTH,
    min_sample: int = DEFAULT_MIN_SAMPLE,
) -> dict[str, RootCause]:
    """Truy vết mọi nút ĐỎ của lớp. Kết quả chỉ chứa nút đỏ có kết luận (đủ mẫu trượt)."""
    out: dict[str, RootCause] = {}
    for y in sorted(k for k, c in colors.items() if c == HeatColor.RED and k in g):
        rc = analyze(g, y, failed.get(y, set()), not_mastered, theta, max_depth, min_sample)
        if rc is not None:
            out[y] = rc
    return out


def alert_message(code: str | None, title: str) -> str:
    """Cảnh báo cho GV (Hình 6.9): "Nên giảng lại N5 Con trỏ"."""
    return f"Nên giảng lại {code} {title}" if code else f"Nên giảng lại {title}"
