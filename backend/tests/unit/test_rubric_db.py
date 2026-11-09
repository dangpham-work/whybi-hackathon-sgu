"""C1-11 – Xong khi: mọi nút có rubric đủ trường và số trang đúng; sinh lại rubric 1 nút; RAG trên pgvector.
Cần TEST_DATABASE_URL."""

import json
from uuid import uuid4

import pytest
from sqlalchemy import func, select

import app.services.rubric as rubric_service
from app.ai.agents.rubric_generator import RubricDraft
from app.ai.agents.tree_builder import ConceptList, MergeDecision, PrereqJudgement, TreeBuilder
from app.ai.providers.fake import _hash_embedding
from app.models.users import ClassSection, DocumentChunk, SyllabusDocument
from app.services.retrieval import RetrievalService
from app.services.storage import InMemoryStorage
from app.services.syllabus import pages_key
from app.workers.documents import InMemoryJobProgress, TreeDrafter
from tests.unit import test_tree_edit_db as _c209
from tests.unit.test_tree_edit_db import DB_URL

world = _c209.world

pytestmark = pytest.mark.skipif(not DB_URL, reason="đặt TEST_DATABASE_URL để chạy trên Postgres thật")

PAGES = [
    {"number": 1, "text": "mở đầu về môn học cấu trúc dữ liệu", "headings": ["Chương 1 Mở đầu"], "ocr": False},
    {"number": 2, "text": "tiếp tục phần mở đầu", "headings": [], "ocr": False},
    {
        "number": 3,
        "text": "con trỏ là biến lưu địa chỉ ô nhớ toán tử lấy địa chỉ",
        "headings": ["Chương 2 Con trỏ"],
        "ocr": False,
    },
    {"number": 4, "text": "mảng là dãy phần tử liên tiếp trong bộ nhớ", "headings": ["Chương 3 Mảng"], "ocr": False},
]


def concept(key, title, desc, chapter):
    return {"key": key, "title": title, "description": desc, "chapter_ref": chapter, "bloom_level": "UNDERSTAND"}


class RagGateway:
    """LLM giả theo kịch bản + embedding băm (truy hồi theo từ chung). `bad_nodes`: nút sinh rubric lỗi."""

    def __init__(self, bad_nodes=()):
        self.bad_nodes = bad_nodes
        self.rubric_prompts = []

    def call_json(self, schema, messages, **kw):
        text = messages[0]["content"]
        if schema is ConceptList:
            by_ref = {
                "Chương 1 Mở đầu": [concept("mo_dau", "Mở đầu", "giới thiệu môn học", "Chương 1")],
                "Chương 2 Con trỏ": [concept("con_tro", "Con trỏ", "biến lưu địa chỉ ô nhớ", "Chương 2")],
                "Chương 3 Mảng": [concept("mang", "Mảng", "dãy phần tử liên tiếp trong bộ nhớ", "Chương 3")],
            }
            ref = next(r for r in by_ref if f"thuộc: {r}." in text)
            return ConceptList.model_validate({"concepts": by_ref[ref]})
        if schema is PrereqJudgement:
            return PrereqJudgement(items=[])
        if schema is MergeDecision:
            return MergeDecision(merge=False)
        assert schema is RubricDraft
        title = text.split('"')[1]
        self.rubric_prompts.append(title)
        if title in self.bad_nodes:
            raise RuntimeError("LLM hỏng")
        return RubricDraft.model_validate(
            {
                "key_points": [{"content": f"Ý chính của {title}"}],
                "scenarios": [{"scenario": f"Tình huống về {title}?", "bloom_level": "APPLY"}] * 3,
                "source_pages": [3, 999],
            }
        )

    def embed(self, texts):
        return [_hash_embedding(t) for t in texts]


def _setup(w, gw, bad=()):
    storage, progress = InMemoryStorage("whybi"), InMemoryJobProgress()
    doc_id = uuid4()
    url = storage.put(f"syllabi/{w.class_id}/{doc_id}.pdf", b"%PDF", "application/pdf")
    doc = SyllabusDocument(
        id=doc_id, class_id=w.class_id, uploaded_by=w.gv, file_url=url, file_type="pdf", status="PARSED"
    )
    w.db.add(doc)
    w.db.commit()
    storage.put(pages_key(w.class_id, doc_id), json.dumps({"pages": PAGES}).encode(), "application/json")
    drafter = TreeDrafter(w.db, storage, progress, TreeBuilder(gw))
    return doc, drafter, progress


def test_truy_hoi_tra_doan_khop_nhat_voi_trang(world):
    gw = RagGateway()
    doc, _, _ = _setup(world, gw)
    svc = RetrievalService(world.db, gw)
    assert svc.index_document(doc.id, PAGES) >= 3 and svc.has_chunks(world.class_id)
    top = svc.retrieve(world.class_id, "con trỏ lưu địa chỉ", 2)
    assert top[0].page_from == 3 and top[0].chapter == "Chương 2 Con trỏ" and top[0].score > top[1].score
    svc.index_document(doc.id, PAGES)  # chạy lại không nhân đôi
    n = world.db.scalar(select(func.count()).select_from(DocumentChunk).where(DocumentChunk.document_id == doc.id))
    assert n == len(svc.retrieve(world.class_id, "x", 50))


def test_moi_nut_co_rubric_du_truong_va_trang_dung(world):
    gw = RagGateway()
    doc, drafter, progress = _setup(world, gw)
    vid = drafter.run(doc.id, "job-1")
    assert vid is not None
    tree = world.api.get(f"/api/v1/classes/{world.class_id}/tree?draft=true").json()
    assert {n["key"] for n in tree["nodes"]} == {"mo_dau", "con_tro", "mang"}
    for n in tree["nodes"]:
        r = n["rubric"]
        assert r["keyPoints"] and len(r["scenarios"]) == 3 and r["approved"] is False
        assert r["sourcePages"] and set(r["sourcePages"]) <= {1, 2, 3, 4}  # trang bịa 999 bị loại
    con_tro = next(n for n in tree["nodes"] if n["key"] == "con_tro")
    assert con_tro["rubric"]["sourcePages"] == [3]
    assert [s for _, _, p in progress.events for s in [p.get("step")]][-3:] == ["RUBRICS", "DONE", None]


def test_nut_loi_rubric_khong_lam_hong_ca_cay_va_bao_gv(world):
    gw = RagGateway(bad_nodes=("Mảng",))
    doc, drafter, _ = _setup(world, gw)
    assert drafter.run(doc.id, "job-2") is not None
    world.db.refresh(doc)
    assert "1 nút chưa sinh được rubric" in doc.error_message
    nodes = world.api.get(f"/api/v1/classes/{world.class_id}/tree?draft=true").json()["nodes"]
    assert {n["key"] for n in nodes if not n["rubric"]} == {"mang"}


def test_sinh_lai_rubric_mot_nut(world, monkeypatch):
    gw = RagGateway()
    doc, drafter, _ = _setup(world, gw)
    drafter.run(doc.id, "job-3")
    monkeypatch.setattr(rubric_service, "get_gateway", lambda: gw)
    nodes = world.api.get(f"/api/v1/classes/{world.class_id}/tree?draft=true").json()["nodes"]
    mang = next(n for n in nodes if n["key"] == "mang")
    world.api.put(f"/api/v1/nodes/{mang['id']}/rubric", json={**mang["rubric"], "approved": True})
    r = world.api.post(f"/api/v1/nodes/{mang['id']}/rubric/regenerate")
    assert r.status_code == 200, r.text
    body = r.json()
    assert (
        body["approved"] is False and body["keyPoints"][0]["id"] == "KP1" and body["sourcePages"] == [3]
    )  # LLM giả luôn trả [3, 999]; 999 bị loại


def test_sinh_lai_quyen_va_khong_co_giao_trinh(world, monkeypatch):
    gw = RagGateway()
    doc, drafter, _ = _setup(world, gw)
    drafter.run(doc.id, "job-4")
    monkeypatch.setattr(rubric_service, "get_gateway", lambda: gw)
    node = world.api.get(f"/api/v1/classes/{world.class_id}/tree?draft=true").json()["nodes"][0]
    world.current = world.gv_other
    assert world.api.post(f"/api/v1/nodes/{node['id']}/rubric/regenerate").json()["error"]["code"] == "NOT_CLASS_OWNER"
    world.current = world.sv
    assert world.api.post(f"/api/v1/nodes/{node['id']}/rubric/regenerate").status_code == 403
    world.current = world.gv
    world.db.execute(DocumentChunk.__table__.delete())
    world.db.commit()
    r = world.api.post(f"/api/v1/nodes/{node['id']}/rubric/regenerate")
    assert r.status_code == 422 and r.json()["error"]["code"] == "NO_SOURCE_MATERIAL"
    assert world.api.post(f"/api/v1/nodes/{uuid4()}/rubric/regenerate").json()["error"]["code"] == "NODE_NOT_FOUND"


def test_cau_hinh_lop_quyet_dinh_nguong_va_so_cau(world):
    cls = world.db.get(ClassSection, world.class_id)
    cls.pass_threshold, cls.challenge_count = 80, 4
    world.db.commit()
    gw = RagGateway()
    doc, drafter, _ = _setup(world, gw)
    drafter.run(doc.id, "job-5")
    r = world.api.get(f"/api/v1/classes/{world.class_id}/tree?draft=true").json()["nodes"][0]["rubric"]
    assert (r["passThreshold"], r["minChallenges"]) == (80, 4)


def test_ai_khong_ghi_de_rubric_gv_vua_duyet(world):
    """GV đã sửa và duyệt rubric một nút; lượt sinh rubric của AI chạy sau (dựng cây / sinh bù) không được ghi đè."""
    from app.api.deps import CurrentUser
    from app.models.enums import Role
    from app.services.skill_tree import SkillTreeService

    gw = RagGateway()
    doc, drafter, _ = _setup(world, gw)
    drafter.run(doc.id, "job-5")
    nodes = world.api.get(f"/api/v1/classes/{world.class_id}/tree?draft=true").json()["nodes"]
    mang = next(n for n in nodes if n["key"] == "mang")
    mine = {**mang["rubric"], "approved": True}
    mine["keyPoints"] = [{"id": "KP1", "content": "GV tự viết", "isRequired": True}]
    assert world.api.put(f"/api/v1/nodes/{mang['id']}/rubric", json=mine).status_code == 200

    user = CurrentUser(id=world.gv, role=Role.LECTURER)
    trees = SkillTreeService(world.db)
    version = trees.get_class_tree(world.class_id, user=user, draft=True)
    drafter._rubrics(trees, world.class_id, version, user)  # lượt AI thứ hai chụp sẵn danh sách nút

    after = next(
        n
        for n in world.api.get(f"/api/v1/classes/{world.class_id}/tree?draft=true").json()["nodes"]
        if n["key"] == "mang"
    )
    assert after["rubric"]["keyPoints"][0]["content"] == "GV tự viết" and after["rubric"]["approved"] is True


def test_loi_truy_hoi_mot_nut_khong_lam_hong_job(world, monkeypatch):
    """Cây đã lưu rồi mà truy hồi RAG của một nút báo lỗi: job vẫn xong, nút đó để trống và GV được báo."""
    from app.core.errors import AppError
    from app.services import retrieval as retrieval_mod

    real = retrieval_mod.RetrievalService.retrieve

    def flaky(self, class_id, query, k, *a, **kw):
        if "Mảng" in query:
            raise AppError(503, "EMBEDDING_UNAVAILABLE", "Dịch vụ nhúng tạm thời không dùng được")
        return real(self, class_id, query, k, *a, **kw)

    monkeypatch.setattr(retrieval_mod.RetrievalService, "retrieve", flaky)
    gw = RagGateway()
    doc, drafter, progress = _setup(world, gw)
    assert drafter.run(doc.id, "job-6") is not None  # trước đây ném AppError ⇒ FAILED dù cây đã lưu
    world.db.refresh(doc)
    assert doc.status == "PARSED" and "1 nút chưa sinh được rubric" in doc.error_message
    nodes = world.api.get(f"/api/v1/classes/{world.class_id}/tree?draft=true").json()["nodes"]
    assert {n["key"] for n in nodes if not n["rubric"]} == {"mang"}
    assert progress.events[-1][1] == "tree.generated" or any(e[1] == "tree.generated" for e in progress.events)


def test_dung_lai_thanh_cong_xoa_thong_bao_loi_cu(world):
    gw = RagGateway()
    doc, drafter, _ = _setup(world, gw)
    doc.error_message = "Đã hủy dựng cây theo yêu cầu"
    world.db.commit()
    assert drafter.run(doc.id, "job-7") is not None
    world.db.refresh(doc)
    assert doc.error_message is None


def test_truy_hoi_co_the_gioi_han_theo_mot_tai_lieu(world):
    """Lớp có hai giáo trình: rubric của tài liệu đang dựng không được trích trang của tài liệu kia."""
    gw = RagGateway()
    doc_a, _, _ = _setup(world, gw)
    doc_b = SyllabusDocument(
        id=uuid4(),
        class_id=world.class_id,
        uploaded_by=world.gv,
        file_url="s3://whybi/syllabi/x/b.pdf",
        file_type="pdf",
        status="PARSED",
    )
    world.db.add(doc_b)
    world.db.commit()
    other = [{"number": 90, "text": "con trỏ trong tài liệu khác hẳn", "headings": ["Chương 9"], "ocr": False}]
    svc = RetrievalService(world.db, gw)
    svc.index_document(doc_a.id, PAGES)
    svc.index_document(doc_b.id, other)
    only_a = svc.retrieve(world.class_id, "con trỏ", 10, document_id=doc_a.id)
    assert only_a and all(p.page_from < 90 for p in only_a)
    both = svc.retrieve(world.class_id, "con trỏ", 10)
    assert any(p.page_from == 90 for p in both)  # không giới hạn thì vẫn thấy cả hai


def test_dung_cay_truy_hoi_rubric_theo_tai_lieu_dang_dung_va_chuong_tu_muc_luc(world, monkeypatch):
    from app.services import retrieval as retrieval_mod
    from app.services.syllabus import toc_key

    seen = []
    real = retrieval_mod.RetrievalService.retrieve

    def spy(self, class_id, query, k, *a, **kw):
        seen.append(kw.get("document_id"))
        return real(self, class_id, query, k, *a, **kw)

    monkeypatch.setattr(retrieval_mod.RetrievalService, "retrieve", spy)
    gw = RagGateway()
    doc, drafter, _ = _setup(world, gw)
    toc = {"chapters": [{"index": 1, "title": "Chương 2. Con trỏ (mục lục)", "startPage": 3, "endPage": 3}]}
    drafter.storage.put(toc_key(world.class_id, doc.id), json.dumps(toc).encode(), "application/json")
    assert drafter.run(doc.id, "job-8") is not None
    assert seen and set(seen) == {doc.id}
    nodes = world.api.get(f"/api/v1/classes/{world.class_id}/tree?draft=true").json()["nodes"]
    con_tro = next(n for n in nodes if n["key"] == "con_tro")
    assert con_tro["chapterRef"] == "Chương 2. Con trỏ (mục lục)"
    assert (con_tro["sourcePageStart"], con_tro["sourcePageEnd"]) == (3, 3)
    mang = next(n for n in nodes if n["key"] == "mang")
    assert mang["chapterRef"] == "Chương 3 Mảng"  # không có trong mục lục ⇒ tiêu đề do hệ thống tách
