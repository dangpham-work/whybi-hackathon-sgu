"""C2-09 – DagValidator (BR-01, mục 5.2.5, 6.1.4). Hàm thuần, không I/O."""

import time

import networkx as nx
import pytest

from app.algorithms.dag import (
    break_cycles,
    build_graph,
    frontier,
    layers,
    sanitize,
    transitive_reduction,
    would_create_cycle,
)
from app.services.skill_tree import load_seed_tree


def g_of(*edges, **attrs) -> nx.DiGraph:
    g = nx.DiGraph()
    for e in edges:
        u, v = e[0], e[1]
        data = e[2] if len(e) > 2 else {}
        g.add_edge(u, v, **({"source": "AI", "confidence": 0.5} | attrs | data))
    return g


@pytest.fixture(scope="module")
def seed_graph() -> nx.DiGraph:
    tree = load_seed_tree()
    g = build_graph(tree)
    return nx.relabel_nodes(g, {n.key: n.code for n in tree.nodes})


# --- would_create_cycle (TC03) ------------------------------------------------------------------


def test_tc03_reverse_edge_returns_cycle_path(seed_graph):
    """Đã có N5 → N6; thêm N6 → N5 tạo chu trình, trả đường đi N6 → N5 → N6."""
    assert would_create_cycle(seed_graph, "N6", "N5") == ["N6", "N5", "N6"]


def test_long_cycle_path_follows_edges(seed_graph):
    path = would_create_cycle(seed_graph, "N11", "N1")
    assert path[0] == "N11" and path[-1] == "N11" and path[1] == "N1"
    for u, v in zip(path[1:-1], path[2:], strict=True):
        assert seed_graph.has_edge(u, v)


def test_valid_edge_returns_none(seed_graph):
    assert would_create_cycle(seed_graph, "N2", "N11") is None


def test_self_loop_is_cycle():
    assert would_create_cycle(nx.DiGraph(), "A", "A") == ["A", "A"]


def test_does_not_mutate_graph(seed_graph):
    before = set(seed_graph.edges)
    would_create_cycle(seed_graph, "N6", "N5")
    assert set(seed_graph.edges) == before


def test_check_under_200ms_on_200_nodes():
    """UC07: kiểm mỗi thao tác thêm cạnh < 200 ms với cây ≤ 200 nút."""
    g = nx.DiGraph()
    nx.add_path(g, [f"n{i}" for i in range(200)])
    for i in range(0, 190, 3):
        g.add_edge(f"n{i}", f"n{i + 7}")
    t = time.perf_counter()
    assert would_create_cycle(g, "n199", "n0") is not None
    assert (time.perf_counter() - t) < 0.2


# --- break_cycles / transitive_reduction / sanitize (6.1.4) -------------------------------------


def test_break_cycles_removes_weakest_ai_edge_first():
    g = g_of(
        ("A", "B", {"source": "LECTURER", "confidence": 0.1}),
        ("B", "C", {"confidence": 0.9}),
        ("C", "A", {"confidence": 0.3}),
    )
    r = break_cycles(g)
    assert nx.is_directed_acyclic_graph(r)
    assert not r.has_edge("C", "A")  # cạnh AI yếu nhất; cạnh của GV giữ dù confidence thấp hơn
    assert r.has_edge("A", "B") and r.has_edge("B", "C")
    assert g.has_edge("C", "A"), "không sửa đồ thị gốc"


def test_transitive_reduction_keeps_attributes_and_isolated_nodes():
    g = g_of(("A", "B"), ("B", "C"), ("A", "C"), confidence=0.8)
    g.add_node("Z", title="lẻ")
    r = transitive_reduction(g)
    assert set(r.edges) == {("A", "B"), ("B", "C")}
    assert r.edges["A", "B"]["confidence"] == 0.8
    assert r.nodes["Z"]["title"] == "lẻ"


def test_sanitize_returns_dag_layers_and_removed_edges():
    g = g_of(("A", "B"), ("B", "C"), ("A", "C"), ("C", "A", {"confidence": 0.1}))
    dag, lay, removed = sanitize(g)
    assert nx.is_directed_acyclic_graph(dag)
    assert ("C", "A") in removed and ("A", "C") in removed
    assert lay == {"A": 0, "B": 1, "C": 2}


def test_layers_of_seed_tree(seed_graph):
    lay = layers(seed_graph)
    assert lay["N1"] == 0 and lay["N2"] == 1 and lay["N5"] == 2
    assert lay["N11"] == max(lay.values())


# --- frontier (mục 2.2.1, Hình 2.2) -------------------------------------------------------------


def test_frontier_example_figure_2_2(seed_graph):
    assert frontier(seed_graph, {"N1", "N3", "N5"}) == {"N2", "N4", "N6"}


def test_frontier_from_scratch_is_roots(seed_graph):
    assert frontier(seed_graph, set()) == {"N1"}
