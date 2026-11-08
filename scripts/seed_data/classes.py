"""Khai báo các lớp demo: môn, GV, cây, tập SV ghi danh, nút điểm nghẽn (root-cause) để demo MX3.

Tập SV của mỗi lớp là một khoảng chỉ số trong users.STUDENTS (có chồng lấp – một SV thật có thể học nhiều môn).
"""

from __future__ import annotations

from dataclasses import dataclass

from . import trees


@dataclass(frozen=True)
class ClassSpec:
    join_code: str
    name: str
    course_code: str
    course_name: str
    lecturer_key: str  # khóa trong users.LECTURERS
    tree_spec: str  # trees.CTDL / trees.NMLT / ...
    base: str | None  # "ctdl" ⇒ mở rộng từ seed/tree_ctdl_gt.json; None ⇒ cây mới hoàn toàn
    student_range: tuple[int, int]  # [start, end) chỉ số trong users.STUDENTS
    root_cause_code: str  # mã nút dồn lỗi để demo cảnh báo "Nên giảng lại X"
    semester: str = "HK1 2026-2027"
    pass_threshold: int = 70


CLASSES: list[ClassSpec] = [
    ClassSpec(
        join_code="CTDL2026",
        name="CTDL&GT – Nhóm 02",
        course_code="COMP1013",
        course_name="Cấu trúc dữ liệu và Giải thuật",
        lecturer_key="an",
        tree_spec=trees.CTDL,
        base="ctdl",
        student_range=(0, 30),
        root_cause_code="N5",
    ),
    ClassSpec(
        join_code="HDH02026",
        name="Hệ điều hành – Nhóm 01",
        course_code="COMP2031",
        course_name="Hệ điều hành",
        lecturer_key="binh",
        tree_spec=trees.HDH,
        base=None,
        student_range=(20, 50),
        root_cause_code="O1",
    ),
    ClassSpec(
        join_code="NMLT2026",
        name="Nhập môn lập trình – Nhóm 01",
        course_code="COMP1001",
        course_name="Nhập môn lập trình",
        lecturer_key="binh",
        tree_spec=trees.NMLT,
        base=None,
        student_range=(45, 75),
        root_cause_code="P6",
    ),
    ClassSpec(
        join_code="MMT02026",
        name="Mạng máy tính – Nhóm 01",
        course_code="COMP2021",
        course_name="Mạng máy tính",
        lecturer_key="an",
        tree_spec=trees.MMT,
        base=None,
        student_range=(60, 90),
        root_cause_code="M8",
    ),
    ClassSpec(
        join_code="CSDL2026",
        name="Cơ sở dữ liệu – Nhóm 01",
        course_code="COMP2011",
        course_name="Cơ sở dữ liệu",
        lecturer_key="binh",
        tree_spec=trees.CSDL,
        base=None,
        student_range=(10, 40),
        root_cause_code="D2",
    ),
]
