"""C2-15 – ghép theo sự kiện: người Đạt dạy tối đa 3 người chưa Đạt, người đến trước được phục vụ trước."""

from app.algorithms.live_matching import TEACH_LIMIT, assign


def test_limit_is_three():
    assert TEACH_LIMIT == 3


def test_one_teacher_takes_at_most_three_learners_first_come_first_served():
    assert assign([("T", 0)], ["a", "b", "c", "d"]) == [("T", "a"), ("T", "b"), ("T", "c")]


def test_load_is_spread_across_teachers():
    pairs = assign([("T1", 0), ("T2", 0)], ["a", "b"])
    assert {t for t, _ in pairs} == {"T1", "T2"}, "mỗi người dạy một bạn, không dồn vào một người"


def test_tie_goes_to_the_teacher_who_passed_earlier():
    assert assign([("T1", 0), ("T2", 0)], ["a"]) == [("T1", "a")]


def test_existing_load_is_counted_and_full_teachers_are_skipped():
    assert assign([("T1", 3), ("T2", 1)], ["a"]) == [("T2", "a")]
    assert assign([("T1", 3)], ["a"]) == []


def test_no_teacher_means_everyone_waits():
    assert assign([], ["a", "b"]) == []


def test_forbidden_pair_is_skipped_but_learner_can_take_another_teacher():
    assert assign([("T1", 0), ("T2", 0)], ["a"], forbidden={("T1", "a")}) == [("T2", "a")]
    assert assign([("T1", 0)], ["a", "b"], forbidden={("T1", "a")}) == [("T1", "b")], (
        "a ở lại hàng chờ, b vẫn được ghép"
    )
