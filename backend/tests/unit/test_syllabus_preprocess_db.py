"""C1-09 – cập nhật trạng thái syllabus_documents khi tiền xử lý (UPLOADED → PARSING → PARSED | FAILED).

Cần Postgres đã migrate (TEST_DATABASE_URL). Dùng lại World của test_tree_edit_db.
"""

from uuid import uuid4

import pytest

from app.api.deps import CurrentUser
from app.core.errors import AppError
from app.models.enums import DocumentStatus, Role
from app.models.users import SyllabusDocument
from app.services.syllabus import SyllabusProcessingRepo, require_job_owner
from tests.unit import test_tree_edit_db as _c209
from tests.unit.test_tree_edit_db import DB_URL

world = _c209.world

pytestmark = pytest.mark.skipif(not DB_URL, reason="đặt TEST_DATABASE_URL để chạy trên Postgres thật")


def _doc(w) -> SyllabusDocument:
    doc = SyllabusDocument(
        id=uuid4(),
        class_id=w.class_id,
        uploaded_by=w.gv,
        file_url=f"s3://whybi/syllabi/{w.class_id}/x.pdf",
        file_type="pdf",
        status=DocumentStatus.UPLOADED,
    )
    w.db.add(doc)
    w.db.commit()  # mark_failed rollback phiên trước khi ghi – bản ghi phải đã commit (savepoint của World)
    return doc


def test_doc_tham_chieu_tai_lieu(world):
    doc = _doc(world)
    ref = SyllabusProcessingRepo(world.db).get(doc.id)
    assert ref.class_id == world.class_id
    assert ref.file_url == doc.file_url
    assert ref.file_type == "pdf"
    assert SyllabusProcessingRepo(world.db).get(uuid4()) is None


def test_chuyen_trang_thai_parsing_roi_parsed(world):
    doc = _doc(world)
    repo = SyllabusProcessingRepo(world.db)
    repo.mark_parsing(doc.id)
    world.db.refresh(doc)
    assert doc.status == DocumentStatus.PARSING
    repo.mark_parsed(doc.id, 12)
    world.db.refresh(doc)
    assert (doc.status, doc.page_count, doc.error_message) == (DocumentStatus.PARSED, 12, None)


def test_chuyen_trang_thai_failed_kem_ly_do(world):
    doc = _doc(world)
    SyllabusProcessingRepo(world.db).mark_failed(doc.id, "PDF có mật khẩu")
    world.db.refresh(doc)
    assert doc.status == DocumentStatus.FAILED
    assert doc.error_message == "PDF có mật khẩu"


# --- Quyền nghe kênh job:{jobId} (jobId = documentId) ---------------------------------------------


def test_gv_da_tai_duoc_nghe_job(world):
    doc = _doc(world)
    require_job_owner(world.db, str(doc.id), CurrentUser(id=world.gv, role=Role.LECTURER))


@pytest.mark.parametrize(
    ("who", "status", "code"),
    [("gv_other", 403, "NOT_CLASS_OWNER"), ("lạ", 404, "JOB_NOT_FOUND"), ("rác", 404, "JOB_NOT_FOUND")],
)
def test_job_cua_nguoi_khac_hoac_khong_co_bi_chan(world, who, status, code):
    doc = _doc(world)
    job_id = {"gv_other": str(doc.id), "lạ": str(uuid4()), "rác": "khong-phai-uuid"}[who]
    user = CurrentUser(id=world.gv_other if who == "gv_other" else world.gv, role=Role.LECTURER)
    with pytest.raises(AppError) as exc:
        require_job_owner(world.db, job_id, user)
    assert (exc.value.status, exc.value.code) == (status, code)
