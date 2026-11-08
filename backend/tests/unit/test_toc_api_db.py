"""Mục lục & cổng cỡ giáo trình qua API: xem báo cáo, chọn khoảng trang rồi dựng cây. Cần TEST_DATABASE_URL."""

import json
from uuid import uuid4

import pytest

from app.api import classes as classes_api
from app.main import app
from app.models.users import SyllabusDocument
from app.services.storage import InMemoryStorage
from app.services.syllabus import InMemoryJobQueue, toc_key
from tests.unit import test_tree_edit_db as _c209
from tests.unit.test_tree_edit_db import DB_URL

world = _c209.world

pytestmark = pytest.mark.skipif(not DB_URL, reason="đặt TEST_DATABASE_URL để chạy trên Postgres thật")

REPORT = {
    "documentId": "x",
    "source": "toc_pages",
    "totalPages": 40,
    "totalChars": 90000,
    "offset": 2,
    "tocPages": [2],
    "level": "WARN",
    "estNodes": 63,
    "estCalls": 140,
    "chapters": [{"index": 1, "title": "Chương 1", "startPage": 3, "endPage": 10, "pages": 8}],
    "advice": {"message": "Nên chọn chương trọng tâm.", "keep": [1], "skip": [], "suggestSplit": False},
    "aiWritten": True,
    "gated": True,
}


@pytest.fixture
def infra(world):
    storage, queue = InMemoryStorage("whybi"), InMemoryJobQueue()
    app.dependency_overrides[classes_api.get_storage] = lambda: storage
    app.dependency_overrides[classes_api.get_job_queue] = lambda: queue
    return storage, queue


def _doc(w, storage, status="PARSED", with_toc=True):
    doc_id = uuid4()
    url = storage.put(f"syllabi/{w.class_id}/{doc_id}.pdf", b"%PDF", "application/pdf")
    doc = SyllabusDocument(
        id=doc_id, class_id=w.class_id, uploaded_by=w.gv, file_url=url, file_type="pdf", status=status, page_count=40
    )
    w.db.add(doc)
    w.db.commit()
    if with_toc:
        storage.put(toc_key(w.class_id, doc_id), json.dumps(REPORT).encode(), "application/json")
    return doc


def _base(w, doc):
    return f"/api/v1/classes/{w.class_id}/syllabi/{doc.id}"


def test_xem_bao_cao_muc_luc(world, infra):
    w, (storage, _) = world, infra
    doc = _doc(w, storage)
    r = w.api.get(f"{_base(w, doc)}/toc")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["level"] == "WARN" and body["gated"] is True and body["chapters"][0]["title"] == "Chương 1"
    assert body["advice"]["keep"] == [1]


def test_chua_co_bao_cao_thi_404_va_gv_khac_bi_chan(world, infra):
    w, (storage, _) = world, infra
    doc = _doc(w, storage, with_toc=False)
    r = w.api.get(f"{_base(w, doc)}/toc")
    assert r.status_code == 404 and r.json()["error"]["code"] == "TOC_NOT_FOUND"
    w.current = w.gv_other
    r = w.api.get(f"{_base(w, doc)}/toc")
    assert r.status_code == 403 and r.json()["error"]["code"] == "NOT_CLASS_OWNER"


def test_chon_khoang_trang_roi_dung_cay_va_bo_co_gated(world, infra):
    w, (storage, queue) = world, infra
    doc = _doc(w, storage)
    r = w.api.post(f"{_base(w, doc)}/build-tree", json={"ranges": [[3, 10], [20, 25]]})
    assert r.status_code == 202, r.text
    assert r.json()["jobId"] == str(doc.id)
    assert queue.builds == [(doc.id, str(doc.id), [[3, 10], [20, 25]], "STANDARD", False)]
    assert json.loads(storage.objects[toc_key(w.class_id, doc.id)])["gated"] is False


def test_khong_chon_gi_thi_dung_tren_toan_bo(world, infra):
    w, (storage, queue) = world, infra
    doc = _doc(w, storage)
    assert w.api.post(f"{_base(w, doc)}/build-tree", json={}).status_code == 202
    assert queue.builds[0][2] is None


@pytest.mark.parametrize("ranges", [[[0, 5]], [[5, 4]], [[30, 41]], [[1]], [[1, 2, 3]]])
def test_khoang_trang_sai_bi_tu_choi(world, infra, ranges):
    w, (storage, queue) = world, infra
    doc = _doc(w, storage)
    r = w.api.post(f"{_base(w, doc)}/build-tree", json={"ranges": ranges})
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_RANGE"
    assert queue.builds == []


def test_chua_boc_chu_xong_thi_chua_dung_duoc(world, infra):
    w, (storage, queue) = world, infra
    doc = _doc(w, storage, status="PARSING")
    r = w.api.post(f"{_base(w, doc)}/build-tree", json={"ranges": []})
    assert r.status_code == 409 and r.json()["error"]["code"] == "DOCUMENT_NOT_READY"
    assert queue.builds == []


def test_chon_muc_chi_tiet_va_hoan_sinh_rubric(world, infra):
    w, (storage, queue) = world, infra
    doc = _doc(w, storage)
    body = {"ranges": [], "detail": "SUMMARY", "lazyRubric": True}
    assert w.api.post(f"{_base(w, doc)}/build-tree", json=body).status_code == 202
    assert queue.builds == [(doc.id, str(doc.id), None, "SUMMARY", True)]


def test_muc_chi_tiet_la_hoac_sai_bi_tu_choi(world, infra):
    w, (storage, queue) = world, infra
    doc = _doc(w, storage)
    r = w.api.post(f"{_base(w, doc)}/build-tree", json={"ranges": [], "detail": "SIEU_CHI_TIET"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert queue.builds == []


def test_tai_lai_trang_van_thay_canh_bao_cua_giao_trinh_moi_nhat(world, infra):
    w, (storage, _) = world, infra
    url = f"/api/v1/classes/{w.class_id}/syllabi/latest/toc"
    assert w.api.get(url).json()["error"]["code"] == "TOC_NOT_FOUND"  # lớp chưa có giáo trình
    cu = _doc(w, storage)
    moi = _doc(w, storage, with_toc=False)
    assert w.api.get(url).status_code == 404  # giáo trình mới nhất chưa có báo cáo ⇒ không lôi báo cáo cũ ra
    storage.put(
        toc_key(w.class_id, moi.id), json.dumps(REPORT | {"documentId": str(moi.id)}).encode(), "application/json"
    )
    got = w.api.get(url)
    assert got.status_code == 200 and got.json()["documentId"] == str(moi.id) != str(cu.id)
    w.current = w.gv_other
    assert w.api.get(url).status_code == 403


def _draft_without_rubrics(w):
    nodes = [{"key": f"n{i}", "title": f"Nút {i}", "bloomLevel": "UNDERSTAND"} for i in (1, 2, 3)]
    r = w.api.post(f"/api/v1/classes/{w.class_id}/tree-versions", json={"nodes": nodes, "edges": []})
    assert r.status_code == 201, r.text


def test_sinh_rubric_cho_nut_con_thieu_xep_hang_mot_lan(world, infra):
    w, (_, queue) = world, infra
    _draft_without_rubrics(w)
    r = w.api.post(f"/api/v1/classes/{w.class_id}/tree/rubrics/generate-missing")
    assert r.status_code == 202 and r.json() == {"missing": 3}
    assert queue.fills == [(w.class_id, w.gv)]


def test_khong_con_nut_thieu_rubric_thi_khong_xep_hang(world, infra):
    w, (_, queue) = world, infra
    _c209._import_seed(w)  # cây mẫu: mọi nút đã có rubric (chưa duyệt)
    r = w.api.post(f"/api/v1/classes/{w.class_id}/tree/rubrics/generate-missing")
    assert r.status_code == 202 and r.json() == {"missing": 0} and queue.fills == []


def test_sinh_rubric_chi_gv_phu_trach_lop(world, infra):
    w, (_, queue) = world, infra
    _draft_without_rubrics(w)
    w.current = w.gv_other
    r = w.api.post(f"/api/v1/classes/{w.class_id}/tree/rubrics/generate-missing")
    assert r.status_code == 403 and queue.fills == []


def test_huy_giao_trinh_dang_xu_ly(world, infra):
    w, (storage, queue) = world, infra
    doc = _doc(w, storage)
    url = f"/api/v1/classes/{w.class_id}/syllabi/{doc.id}/cancel"

    # GV khác không hủy được
    w.current = w.gv_other
    assert w.api.post(url).status_code == 403

    # GV chủ lớp hủy thành công
    w.current = w.gv
    res = w.api.post(url)
    assert res.status_code == 200
    assert res.json() == {"documentId": str(doc.id), "status": "CANCELLED"}
    assert str(doc.id) in queue.cancelled

    # Kiểm tra DB đã cập nhật FAILED và thông báo hủy
    w.db.expire_all()
    reloaded = w.db.get(SyllabusDocument, doc.id)
    assert reloaded.status == "FAILED"
    assert "Đã hủy theo yêu cầu" in reloaded.error_message
