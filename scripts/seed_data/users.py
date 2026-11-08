"""Nguồn tài khoản mẫu dùng chung cho nhiều lớp demo: 2 GV, 1 QTV, 90 SV.

Danh sách cố định (không random) để chạy lại cho ra đúng cùng dữ liệu – seed_db.py bỏ qua bản ghi đã có theo email.
"""

from __future__ import annotations

from dataclasses import dataclass

HO = ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Huỳnh", "Phan", "Vũ", "Võ", "Đặng", "Bùi", "Đỗ", "Ngô", "Dương", "Lý"]
TEN_DEM_NAM = ["Văn", "Minh", "Đức", "Hữu", "Quang", "Thành", "Công", "Gia", "Bảo", "Anh"]
TEN_DEM_NU = ["Thị", "Thu", "Ngọc", "Thanh", "Diễm", "Kim", "Hồng", "Phương", "Mỹ", "Ánh"]
TEN_NAM = [
    "An", "Bình", "Cường", "Dũng", "Đạt", "Hải", "Hùng", "Khang", "Long", "Minh",
    "Nam", "Phúc", "Quân", "Sơn", "Tài", "Tuấn", "Việt", "Vinh",
]  # fmt: skip
TEN_NU = [
    "Anh", "Chi", "Châu", "Giang", "Hà", "Hoa", "Huyền", "Lan", "Linh", "Mai",
    "My", "Nga", "Ngân", "Nhi", "Thảo", "Trang", "Vy", "Yến",
]  # fmt: skip


def _ten(i: int) -> str:
    """Tên đầy đủ tất định theo chỉ số – xen nam/nữ, không lặp trong 90 SV đầu (bộ tên đủ lớn)."""
    ho = HO[i % len(HO)]
    nu = i % 2 == 0
    dem = (TEN_DEM_NU if nu else TEN_DEM_NAM)[i % 10]
    ten = (TEN_NU if nu else TEN_NAM)[(i * 7) % 18]
    return f"{ho} {dem} {ten}"


@dataclass(frozen=True)
class Lecturer:
    email: str
    full_name: str
    faculty: str
    academic_title: str


@dataclass(frozen=True)
class Admin:
    email: str
    full_name: str


@dataclass(frozen=True)
class StudentAcc:
    email: str
    full_name: str
    student_code: str
    cohort: str


ADMIN = Admin(email="admin@whybi.test", full_name="Quản trị Whybi")

LECTURERS: dict[str, Lecturer] = {
    "an": Lecturer(
        email="gv.an@whybi.test",
        full_name="TS. Nguyễn Văn An",
        faculty="Khoa CNTT",
        academic_title="TS.",
    ),
    "binh": Lecturer(
        email="gv.binh@whybi.test",
        full_name="ThS. Trần Thị Bình",
        faculty="Khoa CNTT",
        academic_title="ThS.",
    ),
}

STUDENT_COUNT = 90
STUDENTS: list[StudentAcc] = [
    StudentAcc(
        email=f"sv{i + 1:02d}@whybi.test",
        full_name=_ten(i),
        student_code=f"31224{i + 1:05d}",
        cohort="K22" if i < 45 else "K23",
    )
    for i in range(STUDENT_COUNT)
]
