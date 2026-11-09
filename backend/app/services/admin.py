"""Quản trị: tài khoản, nhập SV từ CSV, danh mục môn, cờ vi phạm, nhật ký (FR-AD-03, 04, 07). Chủ: Long (C2-18).

Mật khẩu ban đầu sinh ngẫu nhiên, trả đúng một lần và không bao giờ ghi vào nhật ký.
"""

import csv
import io
import logging
import secrets
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import hash_password
from app.models.enums import Role
from app.models.peer import AuditLog
from app.models.schemas.admin import (
    AuditLogOut,
    ClassLiteOut,
    CourseIn,
    CourseOut,
    CreatedUser,
    FlagOut,
    ImportedStudent,
    ImportResult,
    RowIssue,
    UserCreate,
    UserOut,
    UserPatch,
    valid_email,
)
from app.models.session import SecurityFlag, TeachingSession
from app.models.users import ClassSection, Course, Lecturer, Student, User
from app.services.auth import student_identities

if TYPE_CHECKING:
    from app.api.deps import CurrentUser
    from app.services.auth import Revocations

log = logging.getLogger(__name__)

MAX_CSV_BYTES = 1_000_000
MAX_CSV_ROWS = 2_000
_PASSWORD_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"  # bỏ ký tự dễ nhầm O/0, l/1/I
_ALIASES = {
    "student_code": {"student_code", "mssv", "ma_sv", "masv", "ma_sinh_vien"},
    "full_name": {"full_name", "ho_ten", "hoten", "ho_va_ten", "ten"},
    "email": {"email", "mail"},
    "cohort": {"cohort", "khoa", "lop"},
}


def new_password() -> str:
    return "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(10))


def _header_map(fields: list[str]) -> dict[str, str]:
    """Tên cột trong tệp → tên chuẩn, không phân biệt hoa thường / khoảng trắng."""
    found: dict[str, str] = {}
    for raw in fields:
        norm = raw.strip().lower().replace(" ", "_").lstrip("﻿")
        for canon, names in _ALIASES.items():
            if norm in names:
                found[raw] = canon
    return found


class AdminService:
    def __init__(self, db: Session, revocations: "Revocations | None" = None) -> None:
        self.db = db
        self.revocations = revocations

    def _revoke_sessions(self, user_id: UUID) -> None:
        """Khóa tài khoản / đặt lại mật khẩu ⇒ mọi access token đang dùng hết hiệu lực ngay (không đợi 30 phút)."""
        if self.revocations is not None:
            self.revocations.revoke_user(str(user_id), datetime.now(UTC).timestamp())

    def audit(
        self, user: "CurrentUser", action: str, entity: str, entity_id: UUID | None, payload: dict | None = None
    ) -> None:
        self.db.add(AuditLog(user_id=user.id, action=action, entity=entity, entity_id=entity_id, payload=payload))

    # ------------------------------------------------------------------ tài khoản

    def _user_out(self, u: User, s: Student | None) -> UserOut:
        return UserOut(
            id=u.id,
            full_name=u.full_name,
            email=u.email,
            role=Role(u.role),
            is_active=u.is_active,
            student_code=s.student_code if s else None,
            cohort=s.cohort if s else None,
            created_at=u.created_at,
        )

    def list_users(
        self, role: Role | None, q: str | None, active: bool | None, limit: int, offset: int
    ) -> list[UserOut]:
        stmt = select(User, Student).join(Student, Student.user_id == User.id, isouter=True)
        if role:
            stmt = stmt.where(User.role == role)
        if active is not None:
            stmt = stmt.where(User.is_active == active)
        if q and q.strip():
            like = f"%{q.strip()}%"
            stmt = stmt.where(or_(User.full_name.ilike(like), User.email.ilike(like), Student.student_code.ilike(like)))
        stmt = stmt.order_by(User.full_name, User.email).limit(limit).offset(offset)
        return [self._user_out(u, s) for u, s in self.db.execute(stmt)]

    def _conflict(self, email: str, code: str | None) -> str | None:
        if self.db.scalar(select(User.id).where(func.lower(User.email) == email)) is not None:
            return "email đã có tài khoản"
        if code and self.db.scalar(select(Student.user_id).where(Student.student_code == code)) is not None:
            return "MSSV đã có tài khoản"
        return None

    def _add_user(
        self, full_name: str, email: str, role: Role, code: str | None, cohort: str | None, password: str
    ) -> tuple[User, Student | None]:
        u = User(full_name=full_name, email=email, password_hash=hash_password(password), role=role)
        self.db.add(u)
        self.db.flush()
        s = None
        if role == Role.STUDENT:
            s = Student(user_id=u.id, student_code=code, cohort=cohort)
            self.db.add(s)
        elif role == Role.LECTURER:
            self.db.add(Lecturer(user_id=u.id))
        self.db.flush()
        return u, s

    def create_user(self, admin: "CurrentUser", body: UserCreate) -> CreatedUser:
        if body.role == Role.STUDENT and not body.student_code:
            raise AppError(422, "STUDENT_CODE_REQUIRED", "Sinh viên cần có MSSV")
        reason = self._conflict(body.email, body.student_code if body.role == Role.STUDENT else None)
        if reason:
            raise AppError(409, "USER_EXISTS", reason.capitalize())
        password = new_password()
        u, s = self._add_user(body.full_name, body.email, body.role, body.student_code, body.cohort, password)
        self.audit(admin, "USER_CREATE", "user", u.id, {"role": body.role, "email": body.email})
        self.db.commit()
        return CreatedUser(user=self._user_out(u, s), password=password)

    def _get_user(self, user_id: UUID) -> tuple[User, Student | None]:
        u = self.db.get(User, user_id)
        if u is None:
            raise AppError(404, "USER_NOT_FOUND", "Không tìm thấy tài khoản")
        return u, self.db.get(Student, user_id)

    def patch_user(self, admin: "CurrentUser", user_id: UUID, body: UserPatch) -> UserOut:
        u, s = self._get_user(user_id)
        if body.is_active is False and u.id == admin.id:
            raise AppError(409, "CANNOT_DEACTIVATE_SELF", "Không thể khóa chính tài khoản đang đăng nhập")
        changes = body.model_dump(exclude_none=True)
        if body.full_name is not None:
            u.full_name = body.full_name
        if body.is_active is not None:
            u.is_active = body.is_active
        self.audit(admin, "USER_UPDATE", "user", u.id, changes)
        if body.is_active is False:
            self._revoke_sessions(u.id)  # trước commit: không có khoảng hở token cũ còn dùng được sau khi khóa
        self.db.commit()
        return self._user_out(u, s)

    def reset_password(self, admin: "CurrentUser", user_id: UUID) -> CreatedUser:
        u, s = self._get_user(user_id)
        password = new_password()
        u.password_hash = hash_password(password)
        self.audit(admin, "USER_RESET_PASSWORD", "user", u.id)
        self._revoke_sessions(u.id)
        self.db.commit()
        return CreatedUser(user=self._user_out(u, s), password=password)

    def import_students(self, admin: "CurrentUser", raw: bytes) -> ImportResult:
        """CSV có tiêu đề: mssv, ho_ten, email, [khoa]. Dòng lỗi không chặn dòng khác."""
        if len(raw) > MAX_CSV_BYTES:
            raise AppError(413, "CSV_TOO_LARGE", "Tệp CSV quá lớn", {"maxBytes": MAX_CSV_BYTES})
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise AppError(422, "CSV_ENCODING", "Tệp CSV phải mã hóa UTF-8") from None
        reader = csv.DictReader(io.StringIO(text))
        cols = _header_map(reader.fieldnames or [])
        missing = {"student_code", "full_name", "email"} - set(cols.values())
        if missing:
            raise AppError(422, "CSV_MISSING_COLUMNS", "Thiếu cột bắt buộc", {"missing": sorted(missing)})

        created: list[ImportedStudent] = []
        skipped: list[RowIssue] = []
        errors: list[RowIssue] = []
        seen_emails: set[str] = set()
        seen_codes: set[str] = set()
        for n, row in enumerate(reader, start=2):
            if n - 1 > MAX_CSV_ROWS:
                raise AppError(413, "CSV_TOO_MANY_ROWS", "Tệp CSV quá nhiều dòng", {"maxRows": MAX_CSV_ROWS})
            r = {cols[k]: (v or "").strip() for k, v in row.items() if k in cols}
            if not any(r.values()):
                continue
            code, name = r.get("student_code", ""), r.get("full_name", "")
            if not code or not name or len(code) > 20 or len(name) > 120:
                errors.append(RowIssue(row=n, reason="thiếu hoặc sai MSSV / họ tên"))
                continue
            try:
                email = valid_email(r.get("email", ""))
            except ValueError:
                errors.append(RowIssue(row=n, reason="email không hợp lệ"))
                continue
            if email in seen_emails or code in seen_codes:
                errors.append(RowIssue(row=n, reason="trùng email hoặc MSSV với dòng trước trong tệp"))
                continue
            seen_emails.add(email)
            seen_codes.add(code)
            reason = self._conflict(email, code)
            if reason:
                skipped.append(RowIssue(row=n, reason=reason))
                continue
            password = new_password()
            self._add_user(name, email, Role.STUDENT, code, r.get("cohort") or None, password)
            created.append(ImportedStudent(row=n, student_code=code, full_name=name, email=email, password=password))
        self.audit(
            admin,
            "USER_IMPORT",
            "user",
            None,
            {"created": len(created), "skipped": len(skipped), "errors": len(errors)},  # không ghi mật khẩu
        )
        self.db.commit()
        return ImportResult(created=created, skipped=skipped, errors=errors)

    # ------------------------------------------------------------------ danh mục môn học

    def list_classes_lite(self) -> list[ClassLiteOut]:
        """Danh sách lớp gọn để QTV chọn khi đặt hạn mức, thay gõ tay UUID (C2-24)."""
        rows = self.db.execute(select(ClassSection.id, ClassSection.name).order_by(ClassSection.name)).all()
        return [ClassLiteOut(id=r.id, name=r.name) for r in rows]

    def list_courses(self) -> list[CourseOut]:
        rows = self.db.scalars(select(Course).order_by(Course.code))
        return [
            CourseOut(id=c.id, code=c.code, name=c.name, credits=c.credits, description=c.description) for c in rows
        ]

    def save_course(self, admin: "CurrentUser", body: CourseIn, course_id: UUID | None = None) -> CourseOut:
        code = body.code.strip()
        dup = select(Course.id).where(func.lower(Course.code) == code.lower())
        if course_id is not None:
            dup = dup.where(Course.id != course_id)
        if self.db.scalar(dup) is not None:
            raise AppError(409, "COURSE_CODE_EXISTS", "Mã môn học đã tồn tại", {"code": code})
        if course_id is None:
            c = Course()
            self.db.add(c)
        else:
            c = self.db.get(Course, course_id)
            if c is None:
                raise AppError(404, "COURSE_NOT_FOUND", "Không tìm thấy môn học")
        c.code, c.name, c.credits, c.description = code, body.name, body.credits, body.description
        self.db.flush()
        self.audit(admin, "COURSE_CREATE" if course_id is None else "COURSE_UPDATE", "course", c.id, {"code": code})
        self.db.commit()
        return CourseOut(id=c.id, code=c.code, name=c.name, credits=c.credits, description=c.description)

    # ------------------------------------------------------------------ cờ vi phạm, nhật ký

    def _flag_rows(self, user: "CurrentUser", resolved: bool, flag_id: UUID | None = None):
        stmt = (
            select(SecurityFlag, TeachingSession.class_id, TeachingSession.student_id)
            .join(TeachingSession, TeachingSession.id == SecurityFlag.session_id)
            .join(ClassSection, ClassSection.id == TeachingSession.class_id)
        )
        if user.role == Role.LECTURER:
            stmt = stmt.where(ClassSection.lecturer_id == user.id)  # GV chỉ thấy cờ của lớp mình
        if flag_id is not None:
            return stmt.where(SecurityFlag.id == flag_id)
        return stmt.where(SecurityFlag.resolved == resolved).order_by(SecurityFlag.created_at.desc())

    def _flag_out(self, rows) -> list[FlagOut]:
        names = student_identities(self.db, {sid for _, _, sid in rows})
        return [
            FlagOut(
                id=f.id,
                session_id=f.session_id,
                turn_id=f.turn_id,
                class_id=cid,
                student_id=sid,
                student_name=names.get(sid, ("", ""))[0],
                type=f.type,
                severity=f.severity,
                detail=f.detail,
                resolved=f.resolved,
                resolved_by=f.resolved_by,
                created_at=f.created_at,
            )
            for f, cid, sid in rows
        ]

    def list_flags(self, user: "CurrentUser", resolved: bool) -> list[FlagOut]:
        return self._flag_out(self.db.execute(self._flag_rows(user, resolved)).all())

    def resolve_flag(self, user: "CurrentUser", flag_id: UUID) -> FlagOut:
        row = self.db.execute(self._flag_rows(user, False, flag_id)).first()
        if row is None:  # không có, hoặc GV không phụ trách lớp chứa cờ – không lộ cờ của lớp khác
            raise AppError(404, "FLAG_NOT_FOUND", "Không tìm thấy cờ vi phạm")
        flag = row[0]
        if not flag.resolved:
            flag.resolved, flag.resolved_by = True, user.id
            self.audit(user, "FLAG_RESOLVE", "security_flag", flag.id, {"type": flag.type})
            self.db.commit()
        return self._flag_out([row])[0]

    def list_audit(self, limit: int, offset: int) -> list[AuditLogOut]:
        rows = self.db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit).offset(offset))
        return [
            AuditLogOut(
                id=a.id,
                user_id=a.user_id,
                action=a.action,
                entity=a.entity,
                entity_id=a.entity_id,
                payload=a.payload,
                created_at=a.created_at,
            )
            for a in rows
        ]
