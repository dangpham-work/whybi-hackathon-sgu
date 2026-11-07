"""SyllabusService – kiểm tệp PDF/DOCX ≤ 20 MB, lưu vào kho đối tượng, tạo bản ghi tài liệu và job (FR-SK-02, 03).
Chủ: Long (C2-08) – phần tải lên; phần xử lý nền (bóc chữ, OCR, chia đoạn) ở `workers/documents.py` (Đăng, C1-09).

Luồng (Hình 4.15): kiểm định dạng + dung lượng → lưu tệp `syllabi/{classId}/{docId}.{ext}` → INSERT
syllabus_documents (UPLOADED) → đẩy task `process_syllabus(documentId, jobId)` vào hàng đợi `documents`
→ 202 {jobId}. Tiến độ phát trên kênh WebSocket `job:{jobId}` (worker phát, C1-09 / C2-13).
"""

import io
import logging
import zipfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import PurePath
from typing import TYPE_CHECKING, BinaryIO, Protocol
from uuid import UUID, uuid4

from kombu.exceptions import KombuError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.models.enums import DocumentStatus, Role
from app.models.users import ClassSection, SyllabusDocument
from app.realtime.gateway import channel_job
from app.services.storage import ObjectStorage, StorageUnavailable

if TYPE_CHECKING:
    from app.api.deps import CurrentUser

log = logging.getLogger(__name__)

MAX_MB = get_settings().max_syllabus_mb
MAX_BYTES = MAX_MB * 1024 * 1024
ALLOWED = ["pdf", "docx"]
CONTENT_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
TASK_PROCESS_SYLLABUS = "app.workers.documents.process_syllabus"


def _invalid(reason: str, message: str) -> AppError:
    return AppError(422, "INVALID_FILE", message, {"reason": reason, "allowed": ALLOWED, "maxMb": MAX_MB})


def _is_docx(data: bytes) -> bool:
    if not data.startswith(b"PK\x03\x04"):
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = set(z.namelist())
    except (zipfile.BadZipFile, ValueError):
        return False
    return {"[Content_Types].xml", "word/document.xml"} <= names


def validate_syllabus(filename: str | None, data: bytes, max_bytes: int = MAX_BYTES) -> str:
    """Trả đuôi chuẩn hóa ("pdf" | "docx"). Sai ⇒ AppError 422 INVALID_FILE / FILE_TOO_LARGE (UC06 – E1, TC01).
    Kiểm cả nội dung (chữ ký tệp), không tin đuôi tên tệp hay Content-Type trình duyệt gửi."""
    if len(data) > max_bytes:
        raise AppError(
            422,
            "FILE_TOO_LARGE",
            f"Tệp vượt quá {max_bytes // (1024 * 1024)} MB",
            {"maxMb": max_bytes // (1024 * 1024), "maxBytes": max_bytes},
        )
    ext = PurePath(filename or "").suffix.lower().lstrip(".")
    if ext not in ALLOWED:
        raise _invalid("EXTENSION", "Chỉ nhận tệp PDF hoặc DOCX")
    if not data:
        raise _invalid("EMPTY", "Tệp rỗng")
    ok = data.startswith(b"%PDF-") if ext == "pdf" else _is_docx(data)
    if not ok:
        raise _invalid("CONTENT_MISMATCH", f"Nội dung tệp không phải {ext.upper()} hợp lệ")
    return ext


class JobQueue(Protocol):
    def enqueue_syllabus(self, document_id: UUID, job_id: str) -> None: ...


class CeleryJobQueue:
    """Đẩy task theo tên (không import mô-đun worker); task_routes đưa vào hàng đợi `documents`.
    job_id dùng làm Celery task_id để đối chiếu log và tiến độ trên kênh WebSocket."""

    def enqueue_syllabus(self, document_id: UUID, job_id: str) -> None:
        from app.workers.celery_app import celery

        # Không dùng pool chung hoặc retry mặc định cho request HTTP. Tiến độ đi qua job:{jobId},
        # không cần đăng ký Redis result backend (on_task_call cũng có vòng retry riêng).
        with celery.connection_for_write(
            connect_timeout=2,
            transport_options={
                "socket_connect_timeout": 2,
                "socket_timeout": 2,
                "retry_on_timeout": False,
                "max_retries": 0,
            },
        ) as connection:
            connection.ensure_connection(max_retries=0)
            celery.send_task(
                TASK_PROCESS_SYLLABUS,
                args=[str(document_id), job_id],
                task_id=job_id,
                connection=connection,
                retry=False,
                ignore_result=True,
            )


class InMemoryJobQueue:
    def __init__(self) -> None:
        self.jobs: list[tuple[UUID, str]] = []

    def enqueue_syllabus(self, document_id: UUID, job_id: str) -> None:
        self.jobs.append((document_id, job_id))


@lru_cache
def default_job_queue() -> JobQueue:
    return InMemoryJobQueue() if get_settings().app_env == "test" else CeleryJobQueue()


def _owned_class(db: Session, class_id: UUID, user: "CurrentUser") -> ClassSection:
    cls = db.get(ClassSection, class_id)
    if cls is None:
        raise AppError(404, "CLASS_NOT_FOUND", "Không tìm thấy lớp", {"classId": str(class_id)})
    if user.role != Role.LECTURER or cls.lecturer_id != user.id:
        raise AppError(403, "NOT_CLASS_OWNER", "Chỉ GV phụ trách lớp được thao tác")
    return cls


@dataclass(frozen=True)
class UploadResult:
    job_id: str
    document_id: UUID

    @property
    def channel(self) -> str:
        return channel_job(self.job_id)


class SyllabusService:
    def __init__(self, db: Session, storage: ObjectStorage, queue: JobQueue, max_bytes: int = MAX_BYTES) -> None:
        self.db = db
        self.storage = storage
        self.queue = queue
        self.max_bytes = max_bytes

    def upload(self, class_id: UUID, filename: str | None, stream: BinaryIO, user: "CurrentUser") -> UploadResult:
        _owned_class(self.db, class_id, user)
        data = stream.read(self.max_bytes + 1)  # đọc tối đa giới hạn + 1 byte là đủ biết quá cỡ
        ext = validate_syllabus(filename, data, self.max_bytes)

        doc_id = uuid4()
        try:
            url = self.storage.put(f"syllabi/{class_id}/{doc_id}.{ext}", data, CONTENT_TYPES[ext])
        except StorageUnavailable as exc:
            log.exception("không lưu được giáo trình lớp %s vào kho đối tượng", class_id)
            raise AppError(503, "STORAGE_UNAVAILABLE", "Kho lưu trữ tệp tạm thời không dùng được") from exc

        doc = SyllabusDocument(
            id=doc_id,
            class_id=class_id,
            uploaded_by=user.id,
            file_url=url,
            file_type=ext,
            status=DocumentStatus.UPLOADED,
        )
        try:
            self.db.add(doc)
            self.db.commit()
        except Exception:
            self.db.rollback()
            self._discard(url)
            raise

        # jobId = documentId: kênh job:{jobId} kiểm quyền được qua bản ghi tài liệu, không cần bảng / khóa Redis riêng.
        job_id = str(doc_id)
        try:
            self.queue.enqueue_syllabus(doc_id, job_id)
        except (KombuError, OSError) as exc:
            log.exception("không đẩy được job xử lý giáo trình %s", doc_id)
            doc.status = DocumentStatus.FAILED
            doc.error_message = "Không đưa được tài liệu vào hàng đợi xử lý – hãy tải lại"
            self.db.commit()
            raise AppError(
                503, "JOB_QUEUE_UNAVAILABLE", "Hàng đợi xử lý tạm thời không dùng được", {"documentId": str(doc_id)}
            ) from exc
        return UploadResult(job_id=job_id, document_id=doc_id)

    def _discard(self, url: str) -> None:
        try:
            self.storage.remove(url)
        except StorageUnavailable:
            log.exception("không xóa được tệp mồ côi %s", url)


# --- Xử lý nền (C1-09, Đăng) ---------------------------------------------------------------------
# Worker `workers/documents.py` đọc / cập nhật syllabus_documents qua lớp này, không truy vấn bảng trực tiếp.


def pages_key(class_id: UUID, document_id: UUID) -> str:
    """Khóa kho đối tượng của văn bản đã bóc theo trang (JSON) – C1-10 đọc lại để trích khái niệm."""
    return f"syllabi/{class_id}/{document_id}.pages.json"


@dataclass(frozen=True)
class DocumentRef:
    id: UUID
    class_id: UUID
    file_url: str
    file_type: str


class SyllabusProcessingRepo:
    """UPLOADED → PARSING → PARSED (kèm page_count) | FAILED (kèm error_message). Mỗi bước commit ngay
    để GV tải lại trang vẫn thấy trạng thái mới nhất."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, document_id: UUID) -> DocumentRef | None:
        doc = self.db.get(SyllabusDocument, document_id)
        if doc is None:
            return None
        return DocumentRef(id=doc.id, class_id=doc.class_id, file_url=doc.file_url, file_type=doc.file_type)

    def _update(self, document_id: UUID, **values: object) -> bool:
        # Khóa và đọc lại để job giao lại / lỗi tới muộn không ghi đè PARSED,
        # kể cả khi phiên đang giữ bản ghi PARSING cũ trong identity map.
        doc = self.db.get(SyllabusDocument, document_id, with_for_update=True, populate_existing=True)
        if doc is None:
            raise LookupError(f"không có syllabus_documents {document_id}")
        if doc.status == DocumentStatus.PARSED:
            self.db.commit()
            return False
        for k, v in values.items():
            setattr(doc, k, v)
        self.db.commit()
        return True

    def mark_parsing(self, document_id: UUID) -> bool:
        return self._update(document_id, status=DocumentStatus.PARSING, error_message=None)

    def mark_parsed(self, document_id: UUID, page_count: int) -> None:
        self._update(document_id, status=DocumentStatus.PARSED, page_count=page_count, error_message=None)

    def mark_failed(self, document_id: UUID, message: str) -> None:
        self.db.rollback()  # lỗi trước đó có thể là lỗi CSDL – phiên phải sạch mới ghi được FAILED
        self._update(document_id, status=DocumentStatus.FAILED, error_message=message)


def require_job_owner(db: Session, job_id: str, user: "CurrentUser") -> None:
    """Chỉ GV phụ trách lớp của tài liệu được nghe job:{jobId} (jobId = documentId) – cổng WebSocket gọi khi
    subscribe. Ném 404 JOB_NOT_FOUND / 403 NOT_CLASS_OWNER."""
    try:
        doc = db.get(SyllabusDocument, UUID(job_id))
    except ValueError:
        doc = None
    if doc is None:
        raise AppError(404, "JOB_NOT_FOUND", "Không tìm thấy job", {"jobId": job_id})
    _owned_class(db, doc.class_id, user)
