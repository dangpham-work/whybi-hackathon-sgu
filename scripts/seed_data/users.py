"""Nguồn tài khoản mẫu dùng chung cho nhiều lớp demo: 2 GV, 1 QTV, 90 SV.

Danh sách cố định (không random) để chạy lại cho ra đúng cùng dữ liệu – seed_db.py bỏ qua bản ghi đã có theo email.
"""

from __future__ import annotations

from dataclasses import dataclass

HO = [
    "Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Huỳnh", "Phan", "Vũ", "Võ", "Đặng",
    "Bùi", "Đỗ", "Hồ", "Ngô", "Dương", "Lý", "Đinh", "Đoàn", "Lâm", "Trịnh",
    "Mai", "Đào", "Cao", "Hà", "Lưu",
]
TEN_DEM_NAM = [
    "Văn", "Minh", "Đức", "Hữu", "Quang", "Thành", "Công", "Gia", "Bảo", "Anh",
    "Quốc", "Tuấn", "Hoàng", "Trọng", "Đình",
]
TEN_DEM_NU = [
    "Thị", "Thu", "Ngọc", "Thanh", "Diễm", "Kim", "Hồng", "Phương", "Mỹ", "Ánh",
    "Thảo", "Khánh", "Tuyết", "Mai", "Như",
]
TEN_NAM = [
    "An", "Bình", "Cường", "Dũng", "Đạt", "Hải", "Hùng", "Khang", "Long", "Minh",
    "Nam", "Phúc", "Quân", "Sơn", "Tài", "Tuấn", "Việt", "Vinh", "Khoa", "Hiếu",
    "Huy", "Thịnh", "Trí", "Kiên", "Lâm", "Tú", "Bách", "Nghĩa", "Phát", "Lộc",
]  # fmt: skip
TEN_NU = [
    "Anh", "Chi", "Châu", "Giang", "Hà", "Hoa", "Huyền", "Lan", "Linh", "Mai",
    "My", "Nga", "Ngân", "Nhi", "Thảo", "Trang", "Vy", "Yến", "Trâm", "Quỳnh",
    "Hương", "Tú", "Tiên", "Vân", "Ngọc", "Duyên", "Đan", "Thy", "Oanh", "Ly",
]  # fmt: skip


def _ten(i: int) -> str:
    """Tên đầy đủ tất định theo chỉ số – xen nam/nữ, 150 tên hoàn toàn khác nhau cho 5 lớp."""
    nu = i % 2 == 0
    ho = HO[i % len(HO)]
    dem = (TEN_DEM_NU if nu else TEN_DEM_NAM)[(i // len(HO)) % 15]
    ten = (TEN_NU if nu else TEN_NAM)[(i * 7 + (i // 5)) % 30]
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
    "cuong": Lecturer(
        email="gv.cuong@whybi.test",
        full_name="TS. Lê Hoàng Cường",
        faculty="Khoa CNTT",
        academic_title="TS.",
    ),
    "dung": Lecturer(
        email="gv.dung@whybi.test",
        full_name="ThS. Phạm Quốc Dũng",
        faculty="Khoa Mạng & Truyền thông",
        academic_title="ThS.",
    ),
    "huong": Lecturer(
        email="gv.huong@whybi.test",
        full_name="TS. Vũ Thị Thu Hương",
        faculty="Khoa Hệ thống thông tin",
        academic_title="TS.",
    ),
}

STUDENT_COUNT = 150
STUDENTS: list[StudentAcc] = [
    StudentAcc(
        email=f"sv{i + 1:02d}@whybi.test",
        full_name=_ten(i),
        student_code=f"31224{i + 1:05d}",
        cohort="K22" if i < 75 else "K23",
    )
    for i in range(STUDENT_COUNT)
]
