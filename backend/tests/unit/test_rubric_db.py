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
