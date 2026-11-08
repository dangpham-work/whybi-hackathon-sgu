"""ClassService – lớp học phần, mã tham gia 8 ký tự, SV tham gia lớp (FR-SK-01, FR-TB-01). Chủ: Long (C2-08).

- Mã tham gia: 8 ký tự từ bảng chữ không gây nhầm (bỏ O/0, I/1), duy nhất (UNIQUE ở CSDL, sinh lại khi trùng).
- SV tham gia lớp xong ⇒ `MasteryService.ensure_student` tạo ô ma trận nếu lớp đã phát hành cây (C2-10).
- Mã sai hoặc lớp đã lưu trữ ⇒ 404 JOIN_CODE_INVALID (không lộ lớp nào tồn tại); đã ở lớp ⇒ 409 ALREADY_ENROLLED.
"""

import secrets
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.algorithms.heatmap import ColorRule
from app.core.errors import AppError
from app.models.enums import Role
from app.models.schemas.heatmap import ClassSettings
from app.models.users import ClassSection, Course, Enrollment
from app.models.users import Lecturer as LecturerProfile
from app.models.users import Student as StudentProfile
from app.services.mastery import MasteryService
from app.services.skill_tree import SkillTreeService

if TYPE_CHECKING:
    from app.api.deps import CurrentUser

JOIN_CODE_LENGTH = 8
JOIN_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_ATTEMPTS = 10
CLASS_ACTIVE = "ACTIVE"  # class_sections.status mặc định; lớp khác ACTIVE (lưu trữ) không nhận SV mới


def new_join_code() -> str:
    return "".join(secrets.choice(JOIN_CODE_ALPHABET) for _ in range(JOIN_CODE_LENGTH))


@dataclass(frozen=True)
class ClassView:
    cls: ClassSection
    student_count: int
    tree_status: str | None


class ClassService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ đọc

    def _views(self, classes: list[ClassSection]) -> list[ClassView]:
        ids = [c.id for c in classes]
        if not ids:
            return []
        q = select(Enrollment.class_id, func.count()).where(Enrollment.class_id.in_(ids)).group_by(Enrollment.class_id)
        counts: dict[UUID, int] = dict(self.db.execute(q).all())
        statuses = SkillTreeService(self.db).statuses_for(ids)
        return [ClassView(c, counts.get(c.id, 0), statuses.get(c.id)) for c in classes]

    def _view(self, cls: ClassSection) -> ClassView:
        return self._views([cls])[0]

    def _get(self, class_id: UUID) -> ClassSection:
        cls = self.db.get(ClassSection, class_id)
        if cls is None:
            raise AppError(404, "CLASS_NOT_FOUND", "Không tìm thấy lớp", {"classId": str(class_id)})
        return cls

    def get_view(self, class_id: UUID) -> ClassView:
        return self._view(self._get(class_id))

    def info(self, class_id: UUID) -> ClassSection:
        """Bản ghi lớp – lời gọi nội bộ (báo cáo C2-20), không kiểm quyền."""
        return self._get(class_id)

    def lecturer_id(self, class_id: UUID) -> UUID:
        """GV phụ trách lớp – lời gọi nội bộ (quyền bản đồ nhiệt C2-13), không kiểm quyền."""
        return self._get(class_id).lecturer_id

    def color_rule(self, class_id: UUID) -> ColorRule:
        """Ngưỡng màu heatmap của lớp (BR-06) – lời gọi nội bộ (HeatmapService C2-11), không kiểm quyền."""
        cls = self._get(class_id)
        return ColorRule.from_class(cls.color_thresholds, cls.min_sample)

    def get_settings(self, class_id: UUID) -> ClassSettings:
        cls = self._get(class_id)
        t = cls.color_thresholds or {}
        return ClassSettings(
            pass_threshold=cls.pass_threshold,
            green_threshold=t.get("green", 0.7),
            yellow_threshold=t.get("yellow", 0.4),
            min_sample=cls.min_sample,
            challenge_count=cls.challenge_count,
        )

    def save_settings(self, class_id: UUID, s: ClassSettings) -> ClassSettings:
        """Ghi cấu hình lớp (chưa commit) – chỉ HeatmapService.update_settings gọi, sau khi kiểm quyền."""
        cls = self._get(class_id)
        cls.pass_threshold = s.pass_threshold
        cls.color_thresholds = {"green": s.green_threshold, "yellow": s.yellow_threshold}
        cls.min_sample = s.min_sample
        cls.challenge_count = s.challenge_count
        self.db.flush()
        return s

    def list_for(self, user: "CurrentUser") -> list[ClassView]:
        """GV-01: lớp GV phụ trách (mới tạo trước). SV-01: lớp SV đã tham gia (mới tham gia trước)."""
        if user.role == Role.LECTURER:
            q = select(ClassSection).where(ClassSection.lecturer_id == user.id).order_by(ClassSection.created_at.desc())
        else:
            q = (
                select(ClassSection)
                .join(Enrollment, Enrollment.class_id == ClassSection.id)
                .where(Enrollment.student_id == user.id)
                .order_by(Enrollment.joined_at.desc())
            )
        return self._views(list(self.db.scalars(q)))

    # ------------------------------------------------------------------ ghi

    def create(self, user: "CurrentUser", course_id: UUID, name: str, semester: str) -> ClassView:
        if self.db.get(LecturerProfile, user.id) is None:
            raise AppError(403, "LECTURER_PROFILE_MISSING", "Tài khoản chưa có hồ sơ giảng viên")
        if self.db.get(Course, course_id) is None:
            raise AppError(404, "COURSE_NOT_FOUND", "Không tìm thấy môn học", {"courseId": str(course_id)})
        for _ in range(_CODE_ATTEMPTS):
            code = new_join_code()
            if self.db.scalar(select(ClassSection.id).where(ClassSection.join_code == code)) is not None:
                continue
            cls = ClassSection(
                id=uuid4(), course_id=course_id, lecturer_id=user.id, name=name, semester=semester, join_code=code
            )
            try:
                with self.db.begin_nested():  # trùng mã do tạo song song ⇒ chỉ hoàn tác savepoint, thử mã khác
                    self.db.add(cls)
            except IntegrityError:
                continue
            self.db.commit()
            return ClassView(cls, 0, None)
        raise AppError(503, "JOIN_CODE_EXHAUSTED", "Không sinh được mã tham gia, hãy thử lại")

    def join(self, user: "CurrentUser", join_code: str) -> ClassView:
        cls = self.db.scalar(select(ClassSection).where(ClassSection.join_code == join_code))
        if cls is None or cls.status != CLASS_ACTIVE:
            raise AppError(404, "JOIN_CODE_INVALID", "Mã tham gia không đúng hoặc lớp đã đóng")
        if self.db.get(StudentProfile, user.id) is None:
            raise AppError(403, "STUDENT_PROFILE_MISSING", "Tài khoản chưa có hồ sơ sinh viên")
        already = AppError(409, "ALREADY_ENROLLED", "Bạn đã ở trong lớp này", {"classId": str(cls.id)})
        enrolled = select(Enrollment.id).where(Enrollment.class_id == cls.id, Enrollment.student_id == user.id)
        if self.db.scalar(enrolled) is not None:
            raise already
        try:
            with self.db.begin_nested():  # hai yêu cầu tham gia song song ⇒ UNIQUE(class_id, student_id) chặn
                self.db.add(Enrollment(class_id=cls.id, student_id=user.id))
        except IntegrityError:
            raise already from None
        # ensure_student commit cả ghi danh lẫn ô ma trận (lớp đã phát hành); lớp chưa phát hành ⇒ tự commit.
        MasteryService(self.db).ensure_student(cls.id, user.id)
        self.db.commit()
        return self._view(cls)

    def archive(self, class_id: UUID, user: "CurrentUser") -> ClassView:
        cls = self._get(class_id)
        if user.role != Role.ADMIN and cls.lecturer_id != user.id:
            raise AppError(403, "NOT_CLASS_OWNER", "Chỉ GV phụ trách lớp hoặc quản trị viên mới có thể lưu trữ lớp")
        cls.status = "ARCHIVED"
        self.db.commit()
        return self._view(cls)

    def restore(self, class_id: UUID, user: "CurrentUser") -> ClassView:
        cls = self._get(class_id)
        if user.role != Role.ADMIN and cls.lecturer_id != user.id:
            raise AppError(403, "NOT_CLASS_OWNER", "Chỉ GV phụ trách lớp hoặc quản trị viên mới có thể khôi phục lớp")
        cls.status = "ACTIVE"
        self.db.commit()
        return self._view(cls)
