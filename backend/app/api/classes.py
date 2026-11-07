"""Lớp học phần, tham gia lớp, tải giáo trình – FR-SK-01…03, FR-TB-01. Chủ: Long (C2-08), Đăng (C1-09)."""

from uuid import UUID

from fastapi import APIRouter, File, UploadFile
from pydantic import Field

from app.api.deps import CurrentUser, Lecturer, LecturerOrStudent, Student
from app.core.errors import NotImplementedYet
from app.models.schemas.common import ApiModel

router = APIRouter(tags=["classes"])


class ClassCreate(ApiModel):
    course_id: UUID
    name: str
    semester: str


class ClassOut(ApiModel):
    id: UUID
    name: str
    semester: str
    join_code: str
    student_count: int = 0
    tree_status: str | None = None


class JoinRequest(ApiModel):
    join_code: str = Field(min_length=8, max_length=8)


class JobAccepted(ApiModel):
    job_id: str
    document_id: UUID


@router.get("/classes", response_model=list[ClassOut])
def list_my_classes(user: CurrentUser = LecturerOrStudent) -> list[ClassOut]:
    """GV-01 / SV-01."""
    raise NotImplementedYet("C2-08")


@router.post("/classes", response_model=ClassOut, status_code=201)
def create_class(body: ClassCreate, user: CurrentUser = Lecturer) -> ClassOut:
    """Tạo lớp, sinh mã tham gia 8 ký tự (FR-SK-01)."""
    raise NotImplementedYet("C2-08")


@router.post("/classes/join", response_model=ClassOut)
def join_class(body: JoinRequest, user: CurrentUser = Student) -> ClassOut:
    """SV tham gia lớp bằng mã (FR-TB-01)."""
    raise NotImplementedYet("C2-08")


@router.post("/classes/{class_id}/syllabi", response_model=JobAccepted, status_code=202)
def upload_syllabus(class_id: UUID, file: UploadFile = File(...), user: CurrentUser = Lecturer) -> JobAccepted:
    """PDF/DOCX ≤ 20 MB → MinIO → job documents; tiến độ qua kênh job:{jobId} (FR-SK-02, 03).
    TC01: tệp .exe đổi đuôi .pdf ⇒ 422 INVALID_FILE."""
    raise NotImplementedYet("C2-08")
