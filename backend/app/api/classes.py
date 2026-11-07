"""Lớp học phần, tham gia lớp, tải giáo trình – FR-SK-01…03, FR-TB-01. Chủ: Long (C2-08), Đăng (C1-09)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import StringConstraints
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, Lecturer, LecturerOrStudent, Student
from app.db.session import get_db
from app.models.schemas.common import ApiModel
from app.services.classes import ClassService, ClassView
from app.services.storage import ObjectStorage, default_storage
from app.services.syllabus import JobQueue, SyllabusService, default_job_queue

router = APIRouter(tags=["classes"])

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Semester = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)]
# Nhận chữ thường / khoảng trắng hai đầu, chuẩn hóa thành 8 chữ IN HOA hoặc số; sai ⇒ 422 VALIDATION_ERROR.
JoinCode = Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Za-z0-9]{8}$")]


class ClassCreate(ApiModel):
    course_id: UUID
    name: Name
    semester: Semester


class ClassOut(ApiModel):
    id: UUID
    name: str
    semester: str
    join_code: str
    student_count: int = 0
    tree_status: str | None = None

    @classmethod
    def of(cls, v: ClassView) -> "ClassOut":
        c = v.cls
        return cls(
            id=c.id,
            name=c.name,
            semester=c.semester,
            join_code=c.join_code,
            student_count=v.student_count,
            tree_status=v.tree_status,
        )


class JoinRequest(ApiModel):
    join_code: JoinCode


class JobAccepted(ApiModel):
    job_id: str
    document_id: UUID
    channel: str  # kênh WebSocket theo dõi tiến độ: job:{jobId}


def get_class_service(db: Session = Depends(get_db)) -> ClassService:
    return ClassService(db)


def get_storage() -> ObjectStorage:
    return default_storage()


def get_job_queue() -> JobQueue:
    return default_job_queue()


def get_syllabus_service(
    db: Session = Depends(get_db),
    storage: ObjectStorage = Depends(get_storage),
    queue: JobQueue = Depends(get_job_queue),
) -> SyllabusService:
    return SyllabusService(db, storage, queue)


Classes = Annotated[ClassService, Depends(get_class_service)]
Syllabi = Annotated[SyllabusService, Depends(get_syllabus_service)]


@router.get("/classes", response_model=list[ClassOut])
def list_my_classes(classes: Classes, user: CurrentUser = LecturerOrStudent) -> list[ClassOut]:
    """GV-01: lớp mình phụ trách. SV-01: lớp đã tham gia."""
    return [ClassOut.of(v) for v in classes.list_for(user)]


@router.post("/classes", response_model=ClassOut, status_code=201)
def create_class(body: ClassCreate, classes: Classes, user: CurrentUser = Lecturer) -> ClassOut:
    """Tạo lớp, sinh mã tham gia 8 ký tự (FR-SK-01). Môn không có ⇒ 404 COURSE_NOT_FOUND."""
    return ClassOut.of(classes.create(user, body.course_id, body.name, body.semester))


@router.post("/classes/join", response_model=ClassOut)
def join_class(body: JoinRequest, classes: Classes, user: CurrentUser = Student) -> ClassOut:
    """SV tham gia lớp bằng mã (FR-TB-01). Sai mã ⇒ 404 JOIN_CODE_INVALID; đã ở lớp ⇒ 409 ALREADY_ENROLLED;
    sai định dạng ⇒ 422 VALIDATION_ERROR."""
    return ClassOut.of(classes.join(user, body.join_code))


@router.post("/classes/{class_id}/syllabi", response_model=JobAccepted, status_code=202)
def upload_syllabus(
    class_id: UUID, syllabi: Syllabi, file: UploadFile = File(...), user: CurrentUser = Lecturer
) -> JobAccepted:
    """PDF/DOCX ≤ 20 MB → kho đối tượng → job documents; tiến độ qua kênh job:{jobId} (FR-SK-02, 03).
    Sai định dạng (kể cả .exe đổi đuôi .pdf – TC01) ⇒ 422 INVALID_FILE; quá 20 MB ⇒ 422 FILE_TOO_LARGE."""
    r = syllabi.upload(class_id, file.filename, file.file, user)
    return JobAccepted(job_id=r.job_id, document_id=r.document_id, channel=r.channel)
