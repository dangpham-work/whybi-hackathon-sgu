"""Lớp học phần, tham gia lớp, tải giáo trình – FR-SK-01…03, FR-TB-01. Chủ: Long (C2-08), Đăng (C1-09)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import StringConstraints
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, Lecturer, LecturerOrAdmin, LecturerOrStudent, Student
from app.db.session import get_db
from app.models.schemas.common import ApiModel
from app.models.schemas.toc import BuildTreeRequest, FillRubricsAccepted, JobCancelledOut, TocReport
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
    status: str = "ACTIVE"

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
            status=c.status,
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


@router.get("/classes/{class_id}", response_model=ClassOut)
def get_class(class_id: UUID, classes: Classes, user: CurrentUser = LecturerOrStudent) -> ClassOut:
    """Chi tiết một lớp học phần."""
    return ClassOut.of(classes.get_view(class_id))


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


@router.get("/classes/{class_id}/syllabi/latest/toc", response_model=TocReport)
def get_latest_syllabus_toc(class_id: UUID, syllabi: Syllabi, user: CurrentUser = Lecturer) -> TocReport:
    """Báo cáo mục lục của giáo trình tải lên gần nhất của lớp – GV tải lại trang GV-03 vẫn thấy cảnh báo đang chờ
    chọn chương. Lớp chưa có giáo trình / chưa có báo cáo ⇒ 404 TOC_NOT_FOUND. Khai báo TRƯỚC `{document_id}`."""
    return TocReport.model_validate(syllabi.latest_toc(class_id, user))


@router.get("/classes/{class_id}/syllabi/{document_id}/toc", response_model=TocReport)
def get_syllabus_toc(class_id: UUID, document_id: UUID, syllabi: Syllabi, user: CurrentUser = Lecturer) -> TocReport:
    """Mục lục chương AI/chương trình đã trích + cảnh báo cỡ giáo trình trước khi dựng cây. Chưa có báo cáo ⇒ 404
    TOC_NOT_FOUND; không phải GV phụ trách lớp ⇒ 403 NOT_CLASS_OWNER."""
    return TocReport.model_validate(syllabi.get_toc(class_id, document_id, user))


@router.post("/classes/{class_id}/syllabi/{document_id}/build-tree", response_model=JobAccepted, status_code=202)
def build_tree_from_syllabus(
    class_id: UUID, document_id: UUID, body: BuildTreeRequest, syllabi: Syllabi, user: CurrentUser = Lecturer
) -> JobAccepted:
    """GV chọn khoảng trang trọng tâm rồi dựng cây (rỗng ⇒ toàn bộ); tiến độ tiếp tục trên kênh job:{jobId}.
    Khoảng trang sai ⇒ 422 INVALID_RANGE; chưa bóc chữ xong ⇒ 409 DOCUMENT_NOT_READY."""
    r = syllabi.request_build(class_id, document_id, body.ranges, user, body.detail, body.lazy_rubric)
    return JobAccepted(job_id=r.job_id, document_id=r.document_id, channel=r.channel)


@router.post("/classes/{class_id}/tree/rubrics/generate-missing", response_model=FillRubricsAccepted, status_code=202)
def generate_missing_rubrics(class_id: UUID, syllabi: Syllabi, user: CurrentUser = Lecturer) -> FillRubricsAccepted:
    """Sinh rubric (chưa duyệt) cho các nút CHƯA có rubric của bản nháp – dùng sau khi dựng cây với lazyRubric và cắt
    tỉa nút. Chạy nền; giao diện hỏi lại cây để thấy rubric xuất hiện. Cây đã phát hành ⇒ 409 TREE_NOT_EDITABLE."""
    return FillRubricsAccepted(missing=syllabi.request_fill_rubrics(class_id, user))


@router.post("/classes/{class_id}/syllabi/{document_id}/cancel", response_model=JobCancelledOut)
def cancel_syllabus_job(
    class_id: UUID, document_id: UUID, syllabi: Syllabi, user: CurrentUser = Lecturer
) -> JobCancelledOut:
    """Hủy tiến trình bóc chữ hoặc dựng cây đang chạy của giáo trình (khi GV tải nhầm tệp hoặc đổi ý)."""
    r = syllabi.cancel(class_id, document_id, user)
    return JobCancelledOut(document_id=r["documentId"], status=r["status"])


@router.post("/classes/{class_id}/archive", response_model=ClassOut)
def archive_class(class_id: UUID, classes: Classes, user: CurrentUser = LecturerOrAdmin) -> ClassOut:
    """Lưu trữ lớp học phần: chuyển sang trạng thái chỉ đọc (FR-SK-01)."""
    return ClassOut.of(classes.archive(class_id, user))


@router.post("/classes/{class_id}/restore", response_model=ClassOut)
def restore_class(class_id: UUID, classes: Classes, user: CurrentUser = LecturerOrAdmin) -> ClassOut:
    """Khôi phục lớp học phần từ kho lưu trữ về trạng thái hoạt động."""
    return ClassOut.of(classes.restore(class_id, user))
