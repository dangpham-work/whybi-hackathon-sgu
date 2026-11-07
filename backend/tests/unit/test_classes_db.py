"""C2-08 – Lớp học phần, tham gia lớp, tải giáo trình (FR-SK-01…03, FR-TB-01).

Xong khi: tệp sai định dạng hoặc quá 20 MB bị từ chối có thông báo; job trả jobId.
Cần Postgres đã migrate (TEST_DATABASE_URL). Dùng lại World của test_tree_edit_db (C2-09).
Kho đối tượng và hàng đợi job thay bằng bản giả qua dependency_overrides.
"""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.api import classes as classes_api
from app.main import app
from app.models.session import MasteryRecord
from app.models.users import ClassSection, Enrollment, SyllabusDocument
from app.services.storage import InMemoryStorage
from app.services.syllabus import CONTENT_TYPES
from tests.unit import test_tree_edit_db as _c209
from tests.unit.test_syllabus_validation import EXE, PDF, docx_bytes
from tests.unit.test_tree_edit_db import DB_URL, _approve_all, _import_seed

world = _c209.world

pytestmark = pytest.mark.skipif(not DB_URL, reason="đặt TEST_DATABASE_URL để chạy trên Postgres thật")


class FakeQueue:
    def __init__(self, fail: bool = False):
        self.jobs: list[tuple[UUID, str]] = []
        self.fail = fail

    def enqueue_syllabus(self, document_id: UUID, job_id: str) -> None:
        if self.fail:
            raise ConnectionError("Redis rớt")
        self.jobs.append((document_id, job_id))


@pytest.fixture
def infra(world):
    storage, queue = InMemoryStorage("whybi"), FakeQueue()
    app.dependency_overrides[classes_api.get_storage] = lambda: storage
    app.dependency_overrides[classes_api.get_job_queue] = lambda: queue
    return storage, queue


def course_id(w) -> UUID:
    return w.db.get(ClassSection, w.class_id).course_id


def join_code(w) -> str:
    return w.db.get(ClassSection, w.class_id).join_code


def docs(w) -> list[SyllabusDocument]:
    return list(w.db.scalars(select(SyllabusDocument).where(SyllabusDocument.class_id == w.class_id)))


# --- Tạo lớp (FR-SK-01) --------------------------------------------------------------------------


def test_create_class_returns_8_char_code_and_lists_for_owner(world):
    r = world.api.post(
        "/api/v1/classes", json={"courseId": str(course_id(world)), "name": "  CTDL&GT – Nhóm 05 ", "semester": "HK1"}
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "CTDL&GT – Nhóm 05" and body["semester"] == "HK1"
    assert len(body["joinCode"]) == 8 and body["joinCode"].isalnum() and body["joinCode"].isupper()
    assert body["studentCount"] == 0 and body["treeStatus"] is None

    listed = world.api.get("/api/v1/classes").json()
    assert {c["id"] for c in listed} == {body["id"], str(world.class_id)}
    old = next(c for c in listed if c["id"] == str(world.class_id))
    assert old["studentCount"] == 1

    world.current = world.gv_other
    assert world.api.get("/api/v1/classes").json() == []


def test_create_class_codes_are_unique(world):
    codes = set()
    for i in range(5):
        body = {"courseId": str(course_id(world)), "name": f"L{i}", "semester": "HK1"}
        r = world.api.post("/api/v1/classes", json=body)
        codes.add(r.json()["joinCode"])
    assert len(codes) == 5


def test_create_class_unknown_course_404(world):
    r = world.api.post("/api/v1/classes", json={"courseId": str(uuid4()), "name": "X", "semester": "HK1"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "COURSE_NOT_FOUND"


def test_create_class_blank_name_422(world):
    r = world.api.post("/api/v1/classes", json={"courseId": str(course_id(world)), "name": "   ", "semester": "HK1"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_tree_status_in_class_list(world):
    _import_seed(world)
    assert world.api.get("/api/v1/classes").json()[0]["treeStatus"] == "DRAFT"


# --- SV tham gia lớp (FR-TB-01) – giả định GD-04 -------------------------------------------------


def test_student_joins_with_code_and_sees_class(world):
    world.current = world.sv_out
    assert world.api.get("/api/v1/classes").json() == []
    r = world.api.post("/api/v1/classes/join", json={"joinCode": join_code(world).lower()})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == str(world.class_id) and body["studentCount"] == 2
    listed = world.api.get("/api/v1/classes").json()
    assert [c["id"] for c in listed] == [str(world.class_id)]


def test_join_twice_409(world):
    world.current = world.sv  # đã ghi danh sẵn trong World
    r = world.api.post("/api/v1/classes/join", json={"joinCode": join_code(world)})
    assert r.status_code == 409 and r.json()["error"]["code"] == "ALREADY_ENROLLED"


def test_join_wrong_code_404(world):
    world.current = world.sv_out
    r = world.api.post("/api/v1/classes/join", json={"joinCode": "ZZZZ9999"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "JOIN_CODE_INVALID"


def test_join_archived_class_404(world):
    world.db.get(ClassSection, world.class_id).status = "ARCHIVED"
    world.db.flush()
    world.current = world.sv_out
    r = world.api.post("/api/v1/classes/join", json={"joinCode": join_code(world)})
    assert r.status_code == 404 and r.json()["error"]["code"] == "JOIN_CODE_INVALID"


@pytest.mark.parametrize("code", ["ABC", "ABCDEFGHI", "CTDL-026"])
def test_join_malformed_code_422(world, code):
    world.current = world.sv_out
    r = world.api.post("/api/v1/classes/join", json={"joinCode": code})
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_lecturer_cannot_join_403(world):
    r = world.api.post("/api/v1/classes/join", json={"joinCode": join_code(world)})
    assert r.status_code == 403


def test_join_after_publish_creates_mastery_cells(world):
    """C2-10: SV vào lớp sau khi đã phát hành ⇒ MasteryService.ensure_student tạo đủ ô."""
    tv = _import_seed(world)
    _approve_all(world, tv)
    assert world.api.post(f"/api/v1/tree-versions/{tv['id']}/publish").status_code == 200
    world.current = world.sv_out
    r = world.api.post("/api/v1/classes/join", json={"joinCode": join_code(world)})
    assert r.status_code == 200 and r.json()["treeStatus"] == "PUBLISHED"
    n = world.db.scalar(select(func.count()).select_from(MasteryRecord).where(MasteryRecord.student_id == world.sv_out))
    assert n == 11
    assert world.api.get(f"/api/v1/classes/{world.class_id}/my-map").status_code == 200


def test_join_before_publish_only_enrolls(world):
    world.current = world.sv_out
    assert world.api.post("/api/v1/classes/join", json={"joinCode": join_code(world)}).status_code == 200
    q = select(Enrollment).where(Enrollment.class_id == world.class_id, Enrollment.student_id == world.sv_out)
    assert world.db.scalar(q) is not None


# --- Tải giáo trình (FR-SK-02, 03) ---------------------------------------------------------------


def upload(w, name: str, data: bytes, ctype: str = "application/pdf", class_id=None):
    cid = class_id or w.class_id
    return w.api.post(f"/api/v1/classes/{cid}/syllabi", files={"file": (name, data, ctype)})


def test_upload_pdf_returns_job_id(world, infra):
    storage, queue = infra
    r = upload(world, "giao-trinh.pdf", PDF)
    assert r.status_code == 202, r.text
    body = r.json()
    job_id, doc_id = body["jobId"], UUID(body["documentId"])
    assert job_id and body["channel"] == f"job:{job_id}"
    assert queue.jobs == [(doc_id, job_id)]
    key = f"syllabi/{world.class_id}/{doc_id}.pdf"
    assert storage.objects[key] == PDF
    [doc] = docs(world)
    assert doc.id == doc_id and doc.status == "UPLOADED" and doc.file_type == "pdf"
    assert doc.file_url == f"s3://whybi/{key}" and doc.uploaded_by == world.gv


def test_upload_docx_ok(world, infra):
    r = upload(world, "giao-trinh.docx", docx_bytes(), CONTENT_TYPES["docx"])
    assert r.status_code == 202, r.text
    assert docs(world)[0].file_type == "docx"


def test_upload_exe_renamed_pdf_rejected_nothing_stored(world, infra):
    storage, queue = infra
    r = upload(world, "giao-trinh.pdf", EXE)
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "INVALID_FILE" and err["message"]
    assert storage.objects == {} and queue.jobs == [] and docs(world) == []


def test_upload_over_20_mb_rejected_nothing_stored(world, infra):
    storage, queue = infra
    r = upload(world, "giao-trinh.pdf", PDF + b"\0" * (20 * 1024 * 1024))
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "FILE_TOO_LARGE" and "20 MB" in err["message"]
    assert storage.objects == {} and queue.jobs == [] and docs(world) == []


def test_upload_by_other_lecturer_403_unknown_class_404(world, infra):
    world.current = world.gv_other
    r = upload(world, "giao-trinh.pdf", PDF)
    assert r.status_code == 403 and r.json()["error"]["code"] == "NOT_CLASS_OWNER"
    world.current = world.gv
    r = upload(world, "giao-trinh.pdf", PDF, class_id=uuid4())
    assert r.status_code == 404 and r.json()["error"]["code"] == "CLASS_NOT_FOUND"


def test_upload_queue_down_503_marks_document_failed(world, infra):
    storage, _ = infra
    app.dependency_overrides[classes_api.get_job_queue] = lambda: FakeQueue(fail=True)
    r = upload(world, "giao-trinh.pdf", PDF)
    assert r.status_code == 503 and r.json()["error"]["code"] == "JOB_QUEUE_UNAVAILABLE"
    [doc] = docs(world)
    assert doc.status == "FAILED" and doc.error_message
