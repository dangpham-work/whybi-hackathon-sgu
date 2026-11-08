"""KT-09: upload → worker → cây/rubric → GV duyệt → bản đồ SV, với Postgres thật.

Đặt TEST_DATABASE_URL tới DB test đã migrate. API/service/worker/gateway chạy thật;
auth, object storage, broker, progress transport và provider được thay bằng bản trong bộ nhớ.
OCR giả chỉ kiểm nhánh xử lý bản quét; ca Tesseract riêng cần binary + vie/eng.
Không đo F1, chất lượng rubric/OCR hoặc độ trễ model bằng các câu trả lời có kịch bản này.
"""

import json
import shutil
from contextlib import contextmanager
from pathlib import Path

import pytest

from app.ai.agents.tree_builder import TreeBuilder
from app.ai.gateway import LLMGateway
from app.ai.providers.base import LLMResult, PermanentProviderError
from app.ai.providers.fake import FakeProvider
from app.api import classes
from app.core.config import get_settings
from app.main import app
from app.models.enums import DocumentStatus
from app.models.users import SyllabusDocument
from app.services import retrieval, rubric
from app.services.storage import InMemoryStorage
from app.services.syllabus import InMemoryJobQueue, SyllabusProcessingRepo
from app.workers import documents
from tests.unit import test_tree_edit_db as tree_db

world = tree_db.world
pytestmark = pytest.mark.skipif(not tree_db.DB_URL, reason="đặt TEST_DATABASE_URL tới Postgres test đã migrate")
SYLLABI = Path(__file__).resolve().parents[3] / "seed" / "syllabi"


class PipelineProvider(FakeProvider):
    """Hai khái niệm và cạnh có chủ đích; đầu ra vẫn qua validation/retry của LLMGateway."""

    def __init__(self):
        self.fail_pointer_rubric = False

    def complete(self, messages, schema, *, model="fake", temperature=0):
        title = schema.get("title")
        if title == "ConceptList":
            data = {
                "concepts": [
                    {
                        "key": "bien",
                        "title": "Biến",
                        "description": "Vùng nhớ lưu dữ liệu có tên.",
                        "chapter_ref": "Chương 1",
                        "bloom_level": "UNDERSTAND",
                    },
                    {
                        "key": "con_tro",
                        "title": "Con trỏ",
                        "description": "Biến lưu địa chỉ của một vùng nhớ.",
                        "chapter_ref": "Chương 1",
                        "bloom_level": "UNDERSTAND",
                    },
                ]
            }
        elif title == "MergeDecision":
            data = {"merge": True}  # cùng khái niệm lặp lại ở các chương của fixture
        elif title == "PrereqJudgement":
            data = {"items": [{"from_key": "bien", "is_prerequisite": True, "confidence": 0.95}]}
        elif title == "RubricDraft":
            if self.fail_pointer_rubric and '"Con trỏ"' in messages[0]["content"]:
                raise PermanentProviderError("lỗi rubric có kịch bản KT-09")
            data = {
                "key_points": [{"content": f"Ý chính mẫu {i}"} for i in range(1, 4)],
                "misconceptions": [{"content": "Nhầm địa chỉ với giá trị", "is_critical": True}],
                "scenarios": [{"scenario": f"Tình huống mẫu {i}?", "bloom_level": "APPLY"} for i in range(1, 4)],
                "source_pages": [1, 999],
            }
        else:
            raise AssertionError(f"Schema ngoài phạm vi pipeline KT-09: {title}")
        return LLMResult(data=data, model="fake")


class ControlledOcr:
    def __init__(self):
        self.calls = 0

    def image_to_text(self, png):
        assert png.startswith(b"\x89PNG\r\n\x1a\n")
        self.calls += 1
        return "Biến lưu dữ liệu. Con trỏ là biến lưu địa chỉ của một vùng nhớ."


class Pipeline:
    def __init__(self, w):
        self.w = w
        self.storage = InMemoryStorage("kt09")
        self.queue = InMemoryJobQueue()
        self.progress = documents.InMemoryJobProgress()
        self.ocr = ControlledOcr()
        self.provider = PipelineProvider()
        self.gateway = LLMGateway(self.provider, max_retries=0, transient_retries=0, cache_size=0)
        self.build_jobs = []

    def upload(self, name, data=None):
        data = (SYLLABI / name).read_bytes() if data is None else data
        response = self.w.api.post(
            f"/api/v1/classes/{self.w.class_id}/syllabi",
            files={"file": (name, data, "application/octet-stream")},
        )
        assert response.status_code == 202, response.text
        accepted = response.json()
        doc_id, job_id = self.queue.jobs[-1]
        assert accepted == {"jobId": job_id, "documentId": str(doc_id), "channel": f"job:{job_id}"}
        assert job_id == str(doc_id)
        doc = self.w.db.get(SyllabusDocument, doc_id)
        assert doc.status == DocumentStatus.UPLOADED
        assert self.storage.get(doc.file_url) == data
        return doc_id, job_id

    def process(self, name, data=None):
        doc_id, job_id = self.upload(name, data)
        documents.process_syllabus.run(str(doc_id), job_id)
        self.w.db.expire_all()
        return self.w.db.get(SyllabusDocument, doc_id), job_id

    def tree(self):
        response = self.w.api.get(f"/api/v1/classes/{self.w.class_id}/tree", params={"draft": "true"})
        assert response.status_code == 200, response.text
        return response.json()


@pytest.fixture
def pipeline(world, monkeypatch):
    p = Pipeline(world)
    # Thử lỗi rubric phải giữ lỗi thật, không đi qua nội dung dự phòng của DEMO_MODE.
    monkeypatch.setattr(get_settings(), "demo_mode", False)
    app.dependency_overrides[classes.get_storage] = lambda: p.storage
    app.dependency_overrides[classes.get_job_queue] = lambda: p.queue
    monkeypatch.setattr(retrieval, "get_gateway", lambda: p.gateway)
    monkeypatch.setattr(rubric, "get_gateway", lambda: p.gateway)

    @contextmanager
    def open_preprocessor():
        yield documents.SyllabusPreprocessor(SyllabusProcessingRepo(world.db), p.storage, p.progress, p.ocr)

    @contextmanager
    def open_tree_drafter():
        yield documents.TreeDrafter(world.db, p.storage, p.progress, TreeBuilder(p.gateway))

    def dispatch_build(*, args, queue):
        p.build_jobs.append((args, queue))
        documents.build_tree.run(*args)

    monkeypatch.setattr(documents, "open_preprocessor", open_preprocessor)
    monkeypatch.setattr(documents, "open_tree_drafter", open_tree_drafter)
    monkeypatch.setattr(documents.build_tree, "apply_async", dispatch_build)
    yield p
    p.gateway.close()


def _assert_draft(p, doc, job_id):
    assert doc.status == DocumentStatus.PARSED and doc.error_message is None
    assert p.build_jobs == [([str(doc.id), job_id], "documents")]
    saved = json.loads(p.storage.get(documents.TreeDrafter.storage_url(doc)))
    assert saved["documentId"] == str(doc.id)
    pages = saved["pages"]
    assert doc.page_count == len(pages) > 0
    assert [page["number"] for page in pages] == list(range(1, len(pages) + 1))
    assert all(page["text"].strip() for page in pages)
    tree = p.tree()
    assert tree["status"] in {"DRAFT", "EDITING"}
    assert {n["key"] for n in tree["nodes"]} == {"bien", "con_tro"}
    assert {(e["fromKey"], e["toKey"]) for e in tree["edges"]} == {("bien", "con_tro")}
    for node in tree["nodes"]:
        r = node["rubric"]
        assert r["approved"] is False
        assert len(r["keyPoints"]) == 3 and len(r["scenarios"]) == 3
        assert r["misconceptions"] and r["minChallenges"] == 3
        assert r["sourcePages"] and set(r["sourcePages"]) <= set(range(1, len(pages) + 1))
    assert all(channel == f"job:{job_id}" for channel, _, _ in p.progress.events)
    assert p.progress.events[-1] == (f"job:{job_id}", "tree.generated", {"versionId": tree["id"]})
    steps = [body.get("step") for _, event, body in p.progress.events if event == "job.progress"]
    assert {"DOWNLOADING", "EXTRACTING", "SAVING", "CONCEPTS", "INDEXING", "RUBRICS", "DONE"} <= set(steps)
    assert "FAILED" not in steps
    return tree, pages


@pytest.mark.parametrize("name", ["01_ctdl_digital.pdf", "02_ctdl_notes.docx", "03_ctdl_scan.pdf"])
def test_upload_workers_generate_draft_and_unapproved_rubrics(pipeline, name):
    p = pipeline
    doc, job_id = p.process(name)
    _, pages = _assert_draft(p, doc, job_id)
    expected_ocr = name == "03_ctdl_scan.pdf"
    assert any(page["ocr"] for page in pages) is expected_ocr
    assert p.ocr.calls == sum(page["ocr"] for page in pages)
    assert (p.ocr.calls > 0) is expected_ocr


def _approve(p, tree):
    for node in tree["nodes"]:
        response = p.w.api.put(f"/api/v1/nodes/{node['id']}/rubric", json=node["rubric"] | {"approved": True})
        assert response.status_code == 200 and response.json()["approved"] is True, response.text


def test_generated_tree_cycle_rejected_then_approval_publishes_student_map(pipeline):
    p = pipeline
    doc, job_id = p.process("01_ctdl_digital.pdf")
    tree, _ = _assert_draft(p, doc, job_id)
    cycle = p.w.api.post(f"/api/v1/tree-versions/{tree['id']}/edges", json={"fromKey": "con_tro", "toKey": "bien"})
    assert cycle.status_code == 409, cycle.text
    assert cycle.json()["error"]["code"] == "CYCLE_DETECTED"
    assert cycle.json()["error"]["details"]["path"] == ["con_tro", "bien", "con_tro"]
    assert p.tree()["edges"] == tree["edges"]
    publish = f"/api/v1/tree-versions/{tree['id']}/publish"
    refused = p.w.api.post(publish)
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "PUBLISH_CHECK_FAILED"
    errors = refused.json()["error"]["details"]["errors"]
    assert {e["nodeKey"] for e in errors if e["code"] == "RUBRIC_NOT_APPROVED"} == {"bien", "con_tro"}
    _approve(p, tree)
    published = p.w.api.post(publish)
    assert published.status_code == 200 and published.json()["status"] == "PUBLISHED", published.text
    p.w.current = p.w.sv
    student_tree = p.w.api.get(f"/api/v1/classes/{p.w.class_id}/tree")
    assert student_tree.status_code == 200 and student_tree.json()["id"] == tree["id"]
    response = p.w.api.get(f"/api/v1/classes/{p.w.class_id}/my-map")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["tree"]["id"] == tree["id"] and result["totalCount"] == 2
    progress = {item["nodeKey"]: item for item in result["progress"]}
    assert progress["bien"]["state"] == "AVAILABLE" and progress["bien"]["canStart"] is True
    assert progress["con_tro"]["state"] == "LOCKED"
    assert progress["con_tro"]["missingPrerequisites"] == ["bien"]


def test_corrupt_pdf_stops_before_tree_job(pipeline):
    p = pipeline
    doc, job_id = p.process("broken.pdf", b"%PDF-1.7\nnot-a-valid-document")
    assert doc.status == DocumentStatus.FAILED and doc.error_message
    assert p.build_jobs == []
    assert p.progress.events[-1][0] == f"job:{job_id}"
    assert p.progress.events[-1][2]["step"] == "FAILED"
    assert not any(event == "tree.generated" for _, event, _ in p.progress.events)
    response = p.w.api.get(f"/api/v1/classes/{p.w.class_id}/tree", params={"draft": "true"})
    assert response.status_code == 404


def test_executable_disguised_as_pdf_is_rejected_before_enqueue(pipeline):
    p = pipeline
    response = p.w.api.post(
        f"/api/v1/classes/{p.w.class_id}/syllabi",
        files={"file": ("disguised.pdf", b"MZ\x00\x00not-a-pdf", "application/pdf")},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "INVALID_FILE"
    assert p.queue.jobs == [] and p.build_jobs == []
    assert not p.w.db.query(SyllabusDocument).filter_by(class_id=p.w.class_id).all()


def test_partial_rubric_failure_is_recoverable_through_regenerate_api(pipeline):
    p = pipeline
    p.provider.fail_pointer_rubric = True
    doc, _ = p.process("01_ctdl_digital.pdf")
    assert doc.status == DocumentStatus.PARSED and "1 nút chưa sinh được rubric" in doc.error_message
    tree = p.tree()
    missing = [node for node in tree["nodes"] if node["rubric"] is None]
    assert [node["key"] for node in missing] == ["con_tro"]
    node_id = missing[0]["id"]
    publish = f"/api/v1/tree-versions/{tree['id']}/publish"
    assert p.w.api.post(publish).status_code == 422
    p.provider.fail_pointer_rubric = False
    regenerated = p.w.api.post(f"/api/v1/nodes/{node_id}/rubric/regenerate")
    assert regenerated.status_code == 200, regenerated.text
    assert regenerated.json()["approved"] is False and len(regenerated.json()["scenarios"]) == 3
    assert p.w.api.post(publish).status_code == 422, "sinh lại không thay cho thao tác duyệt của GV"
    _approve(p, p.tree())
    response = p.w.api.post(publish)
    assert response.status_code == 200 and response.json()["status"] == "PUBLISHED", response.text


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="OCR thật cần Tesseract với vie+eng")
def test_real_tesseract_scan_flows_to_rubrics(pipeline):
    import pytesseract

    if not {"vie", "eng"} <= set(pytesseract.get_languages()):
        pytest.skip("OCR thật cần cả hai gói vie và eng")
    p = pipeline
    p.ocr = documents.TesseractOcr()
    doc, job_id = p.process("03_ctdl_scan.pdf")
    _, pages = _assert_draft(p, doc, job_id)
    assert all(page["ocr"] for page in pages)
    text = " ".join(page["text"] for page in pages).casefold()
    assert "con trỏ" in text
