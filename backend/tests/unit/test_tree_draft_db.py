"""C1-10 – Xong khi: giáo trình đã bóc → cây nháp (hậu xử lý DAG C2-09) + sự kiện
tree.generated. Cần TEST_DATABASE_URL."""

import json
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.ai.agents.rubric_generator import RubricDraft
from app.ai.agents.tree_builder import TreeBuilder
from app.ai.providers.fake import _hash_embedding
from app.models.tree import TreeVersion as OrmTreeVersion
from app.models.users import SyllabusDocument
from app.services.storage import InMemoryStorage
from app.services.syllabus import pages_key
from app.workers.documents import InMemoryJobProgress, TreeDrafter
from tests.ai.test_tree_builder import ScriptedGateway, concept
from tests.unit import test_tree_edit_db as _c209
from tests.unit.test_tree_edit_db import DB_URL

world = _c209.world

pytestmark = pytest.mark.skipif(not DB_URL, reason="đặt TEST_DATABASE_URL để chạy trên Postgres thật")

PAGES = [{"number": 1, "text": "nội dung", "headings": ["Chương 1"], "ocr": False}]


class Gateway(ScriptedGateway):
    """Thêm rubric (C1-11) và embedding 768 chiều để nhúng giáo trình vào pgvector."""

    def call_json(self, schema, messages, **kw):
        if schema is RubricDraft:
            return RubricDraft.model_validate(
                {"key_points": [{"content": "ý"}], "scenarios": [{"scenario": "tình huống?"}]}
            )
        return super().call_json(schema, messages, **kw)

    def embed(self, texts):
        return [_hash_embedding(t) for t in texts]


def _doc(w, storage, pages=PAGES):
    doc_id = uuid4()
    url = storage.put(f"syllabi/{w.class_id}/{doc_id}.pdf", b"%PDF", "application/pdf")
    doc = SyllabusDocument(
        id=doc_id, class_id=w.class_id, uploaded_by=w.gv, file_url=url, file_type="pdf", status="PARSED"
    )
    w.db.add(doc)
    w.db.commit()
    if pages is not None:
        storage.put(pages_key(w.class_id, doc_id), json.dumps({"pages": pages}).encode(), "application/json")
    return doc


def _drafter(w, storage, progress, gw):
    return TreeDrafter(w.db, storage, progress, TreeBuilder(gw))


def test_tao_cay_nhap_pha_chu_trinh_va_phat_tree_generated(world):
    storage, progress = InMemoryStorage("whybi"), InMemoryJobProgress()
    doc = _doc(world, storage)
    gw = Gateway(
        {"Chương 1": [concept("a", "A"), concept("b", "B", desc="cần A"), concept("c", "C", desc="cần B")]},
        vectors={"A": [1, 0, 0], "B": [0, 1, 0], "C": [0, 0, 1]},
        prereq={"B": [("a", True, 0.9)], "C": [("a", True, 0.7), ("b", True, 0.8)]},  # a→c bắc cầu ⇒ bị rút gọn
    )
    vid = _drafter(world, storage, progress, gw).run(doc.id, "job-1")
    v = world.db.get(OrmTreeVersion, vid)
    assert v.status in ("DRAFT", "EDITING")  # put_rubric đánh dấu EDITING; cả hai đều sửa được
    tree = world.api.get(f"/api/v1/classes/{world.class_id}/tree?draft=true").json()
    assert {n["key"] for n in tree["nodes"]} == {"a", "b", "c"}
    assert {(e["fromKey"], e["toKey"]) for e in tree["edges"]} == {("a", "b"), ("b", "c")}
    assert all(e["source"] == "AI" for e in tree["edges"])
    ev = [e for _, e, _ in progress.events]
    assert ev[-1] == "tree.generated" and progress.events[-1][2] == {"versionId": str(vid)}
    assert progress.events[-2][2]["percent"] == 100


def test_thieu_pages_json_bao_loi_cho_gv(world):
    storage, progress = InMemoryStorage("whybi"), InMemoryJobProgress()
    doc = _doc(world, storage, pages=None)
    assert _drafter(world, storage, progress, Gateway({})).run(doc.id, "job-2") is None
    world.db.refresh(doc)
    assert doc.error_message and progress.events[-1][2]["step"] == "FAILED"


def test_khong_trich_duoc_khai_niem_thi_failed_khong_tao_phien_ban(world):
    storage, progress = InMemoryStorage("whybi"), InMemoryJobProgress()
    doc = _doc(world, storage)
    before = len(list(world.db.scalars(select(OrmTreeVersion.id))))
    assert _drafter(world, storage, progress, Gateway({"Chương 1": []})).run(doc.id, "job-3") is None
    world.db.refresh(doc)
    assert "khái niệm" in doc.error_message and progress.events[-1][2]["step"] == "FAILED"
    assert len(list(world.db.scalars(select(OrmTreeVersion.id)))) == before
