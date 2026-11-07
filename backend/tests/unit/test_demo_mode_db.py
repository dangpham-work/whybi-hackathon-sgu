"""C1-13 – Xong khi: ngắt kết nối LLM, kịch bản demo vẫn chạy trọn (tải giáo trình → cây → phiên giảng → kết quả).
Cần TEST_DATABASE_URL."""

import json
from uuid import uuid4

import pytest

from app.ai.agents.tree_builder import TreeBuilder
from app.core.config import get_settings
from app.models.users import SyllabusDocument
from app.services.storage import InMemoryStorage
from app.services.syllabus import pages_key
from app.workers.documents import InMemoryJobProgress, TreeDrafter
from tests.ai.test_demo_mode import GOOD, DeadGateway
from tests.unit import test_session_orchestrator_db as _c107
from tests.unit import test_tree_edit_db as _c209
from tests.unit.test_session_orchestrator_db import DB_URL, node_id, turn

world = _c209.world
bus, completed, published = _c107.bus, _c107.completed, _c107.published

pytestmark = pytest.mark.skipif(not DB_URL, reason="đặt TEST_DATABASE_URL để chạy trên Postgres thật")

PAGES = [{"number": 1, "text": "nội dung giáo trình", "headings": ["Chương 1"], "ocr": False}]


def _drafter(w):
    storage, progress = InMemoryStorage("whybi"), InMemoryJobProgress()
    doc_id = uuid4()
    url = storage.put(f"syllabi/{w.class_id}/{doc_id}.pdf", b"%PDF", "application/pdf")
    doc = SyllabusDocument(
        id=doc_id, class_id=w.class_id, uploaded_by=w.gv, file_url=url, file_type="pdf", status="PARSED"
    )
    w.db.add(doc)
    w.db.commit()
    storage.put(pages_key(w.class_id, doc_id), json.dumps({"pages": PAGES}).encode(), "application/json")
    return doc, TreeDrafter(w.db, storage, progress, TreeBuilder(DeadGateway())), progress


def test_mat_ket_noi_van_ra_cay_mau_co_rubric(world, monkeypatch):
    monkeypatch.setattr(get_settings(), "demo_mode", True)
    doc, drafter, progress = _drafter(world)
    assert drafter.run(doc.id, "job-1") is not None
    nodes = world.api.get(f"/api/v1/classes/{world.class_id}/tree?draft=true").json()["nodes"]
    assert len(nodes) >= 8
    with_rubric = [n for n in nodes if n["rubric"]]
    assert any(n["key"] == "n5_con_tro" for n in with_rubric)
    assert all(n["rubric"]["approved"] is False for n in with_rubric)
    assert progress.events[-1][1] == "tree.generated"


def test_tat_demo_thi_mat_ket_noi_la_failed(world, monkeypatch):
    monkeypatch.setattr(get_settings(), "demo_mode", False)
    doc, drafter, progress = _drafter(world)
    assert drafter.run(doc.id, "job-2") is None
    assert progress.events[-1][2]["step"] == "FAILED"


def test_sinh_lai_rubric_khi_mat_ket_noi_lay_rubric_luu_san(world, monkeypatch):
    import app.services.rubric as rubric_service

    monkeypatch.setattr(get_settings(), "demo_mode", True)
    doc, drafter, _ = _drafter(world)
    drafter.run(doc.id, "job-3")
    monkeypatch.setattr(rubric_service, "get_gateway", lambda: DeadGateway())
    tree = world.api.get(f"/api/v1/classes/{world.class_id}/tree?draft=true").json()
    node = next(n for n in tree["nodes"] if n["key"] == "n5_con_tro")
    r = world.api.post(f"/api/v1/nodes/{node['id']}/rubric/regenerate")
    assert r.status_code == 200 and r.json()["approved"] is False and r.json()["keyPoints"]
    monkeypatch.setattr(get_settings(), "demo_mode", False)
    assert world.api.post(f"/api/v1/nodes/{node['id']}/rubric/regenerate").status_code == 503


def test_phien_giang_tron_ven_khi_mat_ket_noi(published, completed, monkeypatch):
    import app.services.session_orchestrator as orch

    monkeypatch.setattr(get_settings(), "demo_mode", True)
    monkeypatch.setattr(orch, "get_gateway", lambda: DeadGateway())
    w, tree = published
    r = w.api.post("/api/v1/sessions", json={"nodeId": node_id(tree, _c107.ROOT), "inputMode": "TEXT"})
    assert r.status_code == 201, r.text
    sid = r.json()["sessionId"]
    reply = turn(w, sid, GOOD[0], "EXPLANATION").json()
    i = 1
    while reply["status"] != "COMPLETED":
        assert reply["question"]["text"]
        reply = turn(w, sid, GOOD[i % len(GOOD)]).json()
        i += 1
    result = w.api.get(f"/api/v1/sessions/{sid}/result").json()
    assert result["verdict"] in ("PASSED", "NOT_PASSED") and len(result["criteria"]) == 5
    assert completed and completed[-1].session_id.hex == sid.replace("-", "")


def test_phien_tat_demo_mat_ket_noi_van_bao_loi_503(published, monkeypatch):
    import app.services.session_orchestrator as orch

    monkeypatch.setattr(get_settings(), "demo_mode", False)
    monkeypatch.setattr(orch, "get_gateway", lambda: DeadGateway())
    w, tree = published
    r = w.api.post("/api/v1/sessions", json={"nodeId": node_id(tree, _c107.ROOT), "inputMode": "TEXT"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "LLM_UNAVAILABLE"
