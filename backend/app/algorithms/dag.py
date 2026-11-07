"""DagValidator – BR-01, mục 5.2.5 & 6.1.4. Chủ: Long (C2-02, C2-09). Hàm thuần, không I/O.

Mã giả `sanitize(G)` ở mục 6.1.4: phá chu trình tại cạnh AI yếu nhất → rút gọn bắc cầu → xếp tầng.
Kiểm tra mỗi thao tác thêm cạnh < 200 ms (UC07); cây ≤ 200 nút.
Cạnh X → Y nghĩa là phải hiểu X trước khi học Y. Thuộc tính cạnh: `source` ("AI" / "LECTURER"), `confidence`.
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
        g.add_edge(e.from_key, e.to_key, source=str(e.source), confidence=e.confidence)
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

    Cách làm: tìm đường từ `to` tới `from` (BFS, O(V + E)); có đường thì chu trình là from → to → … → from.
    TC03: N6→N5 khi đã có N5→N6 ⇒ ["N6", "N5", "N6"]. Không sửa `g`.
    """
    if from_key == to_key:
        return [from_key, to_key]
    if to_key not in g or from_key not in g:
        return None
    try:
        back = nx.shortest_path(g, to_key, from_key)
    except nx.NetworkXNoPath:
        return None
    return [from_key, *back]


def _weight(g: nx.DiGraph, e: tuple[str, str]) -> float:
    c = g.edges[e].get("confidence")
    return 1.0 if c is None else float(c)


def break_cycles(g: nx.DiGraph) -> nx.DiGraph:
    """Bản sao không chu trình: lặp xóa cạnh confidence thấp nhất của chu trình, ưu tiên cạnh source=AI
    (cạnh GV tự nối chỉ bị xóa khi chu trình toàn cạnh GV)."""
    r = g.copy()
    while True:
        try:
            cycle = [(u, v) for u, v, *_ in nx.find_cycle(r, orientation="original")]
        except nx.NetworkXNoCycle:
            return r
        ai = [e for e in cycle if r.edges[e].get("source", "AI") == "AI"] or cycle
        r.remove_edge(*min(ai, key=lambda e: _weight(r, e)))


def transitive_reduction(g: nx.DiGraph) -> nx.DiGraph:
    """Bỏ A→C khi đã có A→…→C, giữ thuộc tính nút và cạnh. `g` phải là DAG."""
    r = nx.transitive_reduction(g)
    r.add_nodes_from(g.nodes(data=True))
    for u, v in r.edges:
        r.edges[u, v].update(g.edges[u, v])
    return r


def layers(g: nx.DiGraph) -> dict[str, int]:
    """Tầng hiển thị theo nx.topological_generations: nút gốc tầng 0."""
    return {n: i for i, gen in enumerate(nx.topological_generations(g)) for n in gen}


def sanitize(g: nx.DiGraph) -> tuple[nx.DiGraph, dict[str, int], list[tuple[str, str]]]:
    """Mục 6.1.4: phá chu trình → rút gọn bắc cầu → xếp tầng. Trả (DAG, tầng, cạnh đã bỏ)."""
    dag = transitive_reduction(break_cycles(g))
    removed = [e for e in g.edges if not dag.has_edge(*e)]
    return dag, layers(dag), removed


def roots(g: nx.DiGraph) -> set[str]:
    return {n for n in g.nodes if g.in_degree(n) == 0}


def frontier(g: nx.DiGraph, mastered: set[str]) -> set[str]:
    """Biên: nút chưa Đạt nhưng mọi tiên quyết đã Đạt (mục 2.2.1).
    Ví dụ Hình 2.2: mastered={N1,N3,N5} ⇒ {N2,N4,N6}."""
    return {n for n in g.nodes if n not in mastered and all(p in mastered for p in g.predecessors(n))}
