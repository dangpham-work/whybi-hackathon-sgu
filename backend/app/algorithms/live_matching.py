"""Ghép cặp theo sự kiện trong hạn kiểm tra bài cũ của một nút (C2-15). Chủ: Long.

Người Đạt nút là người dạy, người chưa Đạt là người học; một người dạy kèm tối đa TEACH_LIMIT người học cùng lúc.
Đến trước phục vụ trước: người học vào người dạy đang kèm ít nhất còn chỗ, hòa thì người Đạt sớm hơn.
Hàm thuần, không I/O; định danh là chuỗi bất kỳ (service truyền str(uuid)).
"""

TEACH_LIMIT = 3  # một người Đạt giảng tối đa 3 người chưa Đạt


def assign(
    teachers: list[tuple[str, int]],
    learners: list[str],
    limit: int = TEACH_LIMIT,
    forbidden: set[tuple[str, str]] | None = None,
) -> list[tuple[str, str]]:
    """Trả [(người dạy, người học)].

    teachers: (id, số người học đang kèm) theo thứ tự Đạt sớm → muộn. learners: theo thứ tự đến trước.
    forbidden: cặp (người dạy, người học) không ghép lại (vừa từ chối / hết hạn); người học đó thử người dạy khác."""
    forbidden = forbidden or set()
    load = dict(teachers)
    order = {t: i for i, (t, _) in enumerate(teachers)}
    pairs: list[tuple[str, str]] = []
    for learner in learners:
        open_ = [t for t in load if load[t] < limit and (t, learner) not in forbidden]
        if not open_:
            continue  # không còn người dạy hợp lệ cho bạn này – ở lại hàng chờ, bạn sau vẫn có thể được ghép
        t = min(open_, key=lambda t: (load[t], order[t]))
        load[t] += 1
        pairs.append((t, learner))
    return pairs
