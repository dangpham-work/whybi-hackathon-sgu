"""DagValidator – BR-01, mục 5.2.5 & 6.1.4. Chủ: Long (C2-09).

Mã giả `sanitize(G)` ở mục 6.1.4: phá chu trình tại cạnh AI yếu nhất → rút gọn bắc cầu → xếp tầng.
Kiểm tra mỗi thao tác thêm cạnh < 200 ms (UC07); cây ≤ 200 nút.
"""

from typing import TYPE_CHECKING

import networkx as nx

if TYPE_CHECKING:
    from app.models.schemas.tree import TreeVersion


def build_graph(tree: "TreeVersion") -> nx.DiGraph:
    """Dựng đồ thị có hướng theo key nút (C2-02). Thuộc tính cạnh: source, confidence."""
    g = nx.DiGraph()
    for n in tree.nodes:
        g.add_node(n.key, title=n.title)
    for e in tree.edges:
        g.add_edge(e.from_key, e.to_key, source=e.source, confidence=e.confidence)
    return g


def find_cycle(g: nx.DiGraph) -> list[str] | None:
    """Trả một chu trình (danh sách key theo thứ tự) nếu có, ngược lại None – BR-01."""
    try:
        cycle = nx.find_cycle(g, orientation="original")
    except nx.NetworkXNoCycle:
        return None
    return [u for u, _v, _dir in cycle]


def would_create_cycle(g: nx.DiGraph, from_key: str, to_key: str) -> list[str] | None:
    """Trả đường đi chu trình (theo key) nếu thêm from→to tạo chu trình, ngược lại None.
    Cách làm: DFS từ `to` xem có tới được `from` không – O(V + E). TC03: N6→N5 khi đã có N5→N6."""
    raise NotImplementedError("C2-09")


def break_cycles(g: nx.DiGraph) -> nx.DiGraph:
    """Xóa cạnh confidence thấp nhất (ưu tiên cạnh source=AI) cho tới khi hết chu trình."""
    raise NotImplementedError("C2-09")


def transitive_reduction(g: nx.DiGraph) -> nx.DiGraph:
    """Bỏ A→C khi đã có A→…→C, giữ thuộc tính nút và cạnh."""
    raise NotImplementedError("C2-09")


def layers(g: nx.DiGraph) -> dict[str, int]:
    """Tầng hiển thị theo nx.topological_generations."""
    raise NotImplementedError("C2-09")


def frontier(g: nx.DiGraph, mastered: set[str]) -> set[str]:
    """Biên: nút chưa Đạt nhưng mọi tiên quyết đã Đạt (mục 2.2.1).
    Ví dụ Hình 2.2: mastered={N1,N3,N5} ⇒ {N2,N4,N6}."""
    raise NotImplementedError("C2-09")
