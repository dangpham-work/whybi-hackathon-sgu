"""C2-14 – hàm thuần ghép cặp bù trừ (mục 6.6). Xong khi: Ví dụ 6.6.4 (Hình 6.11) ra đúng cặp."""

import pytest

from app.algorithms.matching import complementarity, node_priority, run_round

# Hình 6.11: Đ = Đạt, B = Biên, K = Khóa (ma trận rút gọn 4 nút)
STUDENTS = ["An", "Chau", "Ha", "Dung", "Khang"]
MASTERED = {
    "An": {"N2", "N5"},
    "Chau": {"N2", "N4"},
    "Ha": set(),
    "Dung": {"N2", "N4", "N5"},
    "Khang": {"N2"},
}
FRONTIER = {
    "An": {"N4", "N6"},
    "Chau": {"N5"},
    "Ha": {"N2", "N4", "N5"},
    "Dung": {"N6"},
    "Khang": set(),
}
# p(N5) = 1,68; p(N4) = 1,33; p(N2) = 1,12; p(N6) = 1,75 (α = 1)
PASS_RATE = {"N2": 0.88, "N4": 0.67, "N5": 0.32, "N6": 0.25}


def test_node_priority_formula():
    p = node_priority(PASS_RATE)
    assert p == pytest.approx({"N2": 1.12, "N4": 1.33, "N5": 1.68, "N6": 1.75})
    assert node_priority({"N1": 0.5}, alpha=2.0) == pytest.approx({"N1": 2.0})


def test_complementarity_is_min_of_both_directions():
    p = node_priority(PASS_RATE)
    assert complementarity("An", "Chau", MASTERED, FRONTIER, p) == pytest.approx(1.33)
    assert complementarity("Chau", "An", MASTERED, FRONTIER, p) == pytest.approx(1.33)
    # một chiều ⇒ 0 (BR-08)
    assert complementarity("Dung", "Ha", MASTERED, FRONTIER, p) == 0
    assert complementarity("An", "Ha", MASTERED, FRONTIER, p) == 0
    assert complementarity("Dung", "An", MASTERED, FRONTIER, p) == 0


def test_example_6_6_4_pairs():
    pairs, waiting = run_round(STUDENTS, MASTERED, FRONTIER, PASS_RATE, recent_pairs=set())
    two_way = [x for x in pairs if not x.one_way]
    assert len(two_way) == 1
    pr = two_way[0]
    assert {pr.a, pr.b} == {"An", "Chau"} and pr.weight == pytest.approx(1.33)
    teaches = {pr.a: pr.a_teaches, pr.b: pr.b_teaches}
    assert teaches == {"An": ["N5"], "Chau": ["N4"]}

    one_way = [x for x in pairs if x.one_way]
    assert len(one_way) == 1
    ow = one_way[0]
    assert (ow.a, ow.b) == ("Dung", "Ha"), "Dũng là mentor, Hà là người học"
    assert ow.a_teaches == ["N5", "N4"], "tối đa 2 nút có p cao nhất"
    assert ow.b_teaches == []
    assert waiting == ["Khang"], "Khang chưa có nút Biên chung – chờ vòng sau"


def test_recent_pair_is_skipped():
    pairs, waiting = run_round(STUDENTS, MASTERED, FRONTIER, PASS_RATE, recent_pairs={frozenset({"An", "Chau"})})
    assert not [x for x in pairs if not x.one_way]
    assert all({x.a, x.b} != {"An", "Chau"} for x in pairs)


def test_max_weight_beats_greedy():
    """Ghép tối ưu cả lớp: chọn A–B trước thì C, D không còn cặp; tối ưu là A–C + B–D (2 + 2 = 4)."""
    mastered = {"A": {"x", "y"}, "B": {"z"}, "C": {"w"}, "D": {"v"}}
    frontier = {"A": {"z", "w"}, "B": {"x", "v"}, "C": {"y"}, "D": {"z"}}
    rate = {k: 0.0 for k in "xyzwv"}  # p = 2 mọi nút
    # A–B: A→B {x}=2, B→A {z}=2 ⇒ 2; A–C: A→C {y}=2, C→A {w}=2 ⇒ 2; B–D: B→D {z}=2, D→B {v}=2 ⇒ 2
    pairs, waiting = run_round(["A", "B", "C", "D"], mastered, frontier, rate, set())
    got = {frozenset({x.a, x.b}) for x in pairs if not x.one_way}
    assert got == {frozenset({"A", "C"}), frozenset({"B", "D"})}
    assert waiting == []


def test_empty_and_single_student():
    assert run_round([], {}, {}, {}, set()) == ([], [])
    pairs, waiting = run_round(["A"], {"A": set()}, {"A": {"x"}}, {"x": 0.5}, set())
    assert pairs == [] and waiting == ["A"]


def test_100_students_under_2_seconds():
    import random
    import time

    rnd = random.Random(7)
    nodes = [f"n{i}" for i in range(30)]
    students = [f"s{i}" for i in range(100)]
    mastered = {s: set(rnd.sample(nodes, rnd.randint(0, 15))) for s in students}
    frontier = {s: set(rnd.sample([n for n in nodes if n not in mastered[s]], 5)) for s in students}
    rate = {n: rnd.random() for n in nodes}
    t0 = time.perf_counter()
    pairs, waiting = run_round(students, mastered, frontier, rate, set())
    assert time.perf_counter() - t0 < 2.0
    used = [s for x in pairs for s in (x.a, x.b)]
    assert len(used) == len(set(used)), "mỗi SV tối đa một cặp"
    assert set(used) | set(waiting) == set(students)


def test_priority_node_wins_contention():
    """C2-15: x ghép được với y (dạy N5) hoặc z (dạy N6). N6 nghẽn hơn ⇒ mặc định chọn z; ưu tiên N5 ⇒ chọn y."""
    students = ["x", "y", "z"]
    mastered = {"x": {"N5", "N6"}, "y": {"N7"}, "z": {"N8"}}
    frontier = {"x": {"N7", "N8"}, "y": {"N5"}, "z": {"N6"}}
    rate = {"N5": 0.5, "N6": 0.1, "N7": 0.0, "N8": 0.0}
    base, _ = run_round(students, mastered, frontier, rate, set())
    assert {base[0].a, base[0].b} == {"x", "z"}
    prio, _ = run_round(students, mastered, frontier, rate, set(), priority_node="N5")
    assert {prio[0].a, prio[0].b} == {"x", "y"}


def test_priority_node_formula_adds_boost_even_for_unknown_rate():
    p = node_priority({"N1": 0.5}, priority_node="N1")
    assert p["N1"] == pytest.approx(1.5 + 10.0)
    assert node_priority({"N1": 0.5}, priority_node="NX")["NX"] == pytest.approx(11.0)
