"""C1-09 – Tiền xử lý giáo trình (FR-SK-03, mục 6.1.1).

Xong khi: PDF số, DOCX và 1 bản quét đều ra văn bản theo trang; GV thấy thanh tiến độ chạy (kênh job:{jobId}).
Tệp mẫu sinh ngay trong test bằng PyMuPDF / python-docx. OCR dùng bản giả; test Tesseract thật tự bỏ qua
khi máy không có `tesseract` + gói `vie` (Docker backend có sẵn).
"""

import io
import json
import shutil
from dataclasses import dataclass, field
from unittest.mock import Mock
from uuid import UUID, uuid4

import docx
import pymupdf
import pytest
from docx.enum.text import WD_BREAK
from docx.oxml import OxmlElement

from app.models.enums import DocumentStatus
from app.models.schemas.mastery import JobProgress
from app.realtime import gateway
from app.services.storage import InMemoryStorage, StorageUnavailable
from app.services.syllabus import DocumentRef, SyllabusProcessingRepo, pages_key
from app.workers import documents
from app.workers.documents import (
    ExtractionError,
    InMemoryJobProgress,
    OcrError,
    RedisJobProgress,
    SyllabusPreprocessor,
    extract_docx,
    extract_pdf,
)

# --- Tệp mẫu ------------------------------------------------------------------------------------


def make_pdf(pages: list[str], *, heading: str | None = None) -> bytes:
    doc = pymupdf.open()
    for i, body in enumerate(pages):
        page = doc.new_page()
        y = 72
        if heading and i == 0:
            page.insert_text((72, y), heading, fontsize=20)
            y += 40
        page.insert_text((72, y), body, fontsize=11)
    return doc.tobytes()


def scanned_page_png(text: str) -> bytes:
    """Ảnh của một trang có chữ – mô phỏng trang quét (không còn lớp chữ)."""
    src = pymupdf.open(stream=make_pdf([text]), filetype="pdf")
    return src[0].get_pixmap(dpi=100).tobytes("png")


def make_pdf_mixed(pages: list[tuple[str, str]]) -> bytes:
    """pages: [("text", nội dung) | ("scan", nội dung) | ("blank", "")]."""
    doc = pymupdf.open()
    for kind, body in pages:
        page = doc.new_page()
        if kind == "text":
            page.insert_text((72, 72), body, fontsize=11)
        elif kind == "scan":
            page.insert_image(page.rect, stream=scanned_page_png(body))
    return doc.tobytes()


def make_docx(blocks: list[tuple[str, str]]) -> bytes:
    """blocks: [("h1", tiêu đề) | ("p", đoạn) | ("break", "") | ("table", "a|b;c|d")]."""
    d = docx.Document()
    for kind, text in blocks:
        if kind == "h1":
            d.add_heading(text, 1)
        elif kind == "p":
            d.add_paragraph(text)
        elif kind == "break":
            d.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        elif kind == "table":
            rows = [r.split("|") for r in text.split(";")]
            t = d.add_table(rows=len(rows), cols=len(rows[0]))
            for r, row in enumerate(rows):
                for c, val in enumerate(row):
                    t.cell(r, c).text = val
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


class FakeOcr:
    def __init__(self, text: str = "Cay nhi phan tim kiem (OCR)", error: Exception | None = None):
        self.text = text
        self.error = error
        self.calls = 0

    def image_to_text(self, png: bytes) -> str:
        self.calls += 1
        assert png.startswith(b"\x89PNG")
        if self.error:
            raise self.error
        return self.text


# --- PDF số ---------------------------------------------------------------------------------------


def test_pdf_so_ra_van_ban_theo_trang():
    ocr = FakeOcr()
    pages = extract_pdf(make_pdf(["Mang va danh sach lien ket", "Ngan xep va hang doi", "Cay nhi phan"]), ocr)
    assert [p.number for p in pages] == [1, 2, 3]
    assert "Ngan xep" in pages[1].text
    assert not any(p.ocr for p in pages)
    assert ocr.calls == 0


def test_pdf_nhan_tieu_de_theo_co_chu():
    pages = extract_pdf(make_pdf(["Noi dung than bai " * 3], heading="Chuong 1 Gioi thieu"), FakeOcr())
    assert pages[0].headings == ["Chuong 1 Gioi thieu"]


# --- Bản quét -------------------------------------------------------------------------------------


def test_ban_quet_chay_ocr_tung_trang():
    ocr = FakeOcr()
    pages = extract_pdf(make_pdf_mixed([("text", "Trang so co chu that day du"), ("scan", "Trang quet")]), ocr)
    assert ocr.calls == 1
    assert pages[0].ocr is False and "Trang so" in pages[0].text
    assert pages[1].ocr is True and pages[1].text == "Cay nhi phan tim kiem (OCR)"


def test_trang_trang_khong_anh_thi_khong_ocr():
    ocr = FakeOcr()
    pages = extract_pdf(make_pdf_mixed([("blank", "")]), ocr)
    assert ocr.calls == 0
    assert pages[0].text == ""


def test_bao_tien_do_tung_trang():
    seen: list[tuple[int, int, bool]] = []
    extract_pdf(
        make_pdf_mixed([("text", "a" * 80), ("scan", "x")]), FakeOcr(), on_page=lambda i, n, o: seen.append((i, n, o))
    )
    assert seen == [(1, 2, False), (2, 2, True)]


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="máy chưa cài tesseract (Docker backend có sẵn)")
def test_tesseract_that_doc_duoc_ban_quet():
    import pytesseract

    if "vie" not in pytesseract.get_languages():
        pytest.skip("thiếu gói ngôn ngữ vie")
    doc = pymupdf.open()
    page = doc.new_page()
    src = pymupdf.open(stream=make_pdf(["Cay nhi phan tim kiem"]), filetype="pdf")
    page.insert_image(page.rect, stream=src[0].get_pixmap(dpi=300).tobytes("png"))
    pages = extract_pdf(doc.tobytes(), documents.TesseractOcr())
    assert pages[0].ocr is True
    assert "nhi phan" in pages[0].text.lower()


# --- DOCX -----------------------------------------------------------------------------------------


def test_docx_chia_trang_theo_ngat_trang():
    data = make_docx(
        [
            ("h1", "Chuong 1 Mang"),
            ("p", "Mang luu phan tu lien tiep"),
            ("break", ""),
            ("h1", "Chuong 2 Danh sach"),
            ("table", "CLO|Mo ta;CLO1|Cai dat danh sach"),
            ("break", ""),
            ("p", "Bai tap"),
        ]
    )
    pages = extract_docx(data)
    assert [p.number for p in pages] == [1, 2, 3]
    assert "Mang luu phan tu" in pages[0].text
    assert pages[0].headings == ["Chuong 1 Mang"]
    assert pages[1].headings == ["Chuong 2 Danh sach"]
    assert "CLO1 | Cai dat danh sach" in pages[1].text
    assert pages[2].text.strip() == "Bai tap"


def test_docx_khong_ngat_trang_la_mot_trang():
    pages = extract_docx(make_docx([("p", "Mot"), ("p", "Hai")]))
    assert len(pages) == 1
    assert pages[0].text.splitlines() == ["Mot", "Hai"]


def test_docx_ngat_trang_do_word_dung_khong_dem_hai_lan():
    """Word lưu cả ngắt cứng (w:br page) lẫn vị trí ngắt đã dàn trang (w:lastRenderedPageBreak) – chỉ đếm một."""
    d = docx.Document()
    d.add_paragraph("Trang mot")
    p = d.add_paragraph()
    p.add_run().add_break(WD_BREAK.PAGE)
    r = p.add_run("Trang hai")
    r._r.insert(0, OxmlElement("w:lastRenderedPageBreak"))
    p3 = d.add_paragraph()
    r3 = p3.add_run("Trang ba (Word tu dan)")
    r3._r.insert(0, OxmlElement("w:lastRenderedPageBreak"))
    buf = io.BytesIO()
    d.save(buf)
    pages = extract_docx(buf.getvalue())
    assert [p.text.strip() for p in pages] == ["Trang mot", "Trang hai", "Trang ba (Word tu dan)"]


# --- Tệp hỏng -------------------------------------------------------------------------------------


def test_pdf_hong_bao_loi_trich_xuat():
    with pytest.raises(ExtractionError):
        extract_pdf(b"%PDF-1.7\nrac rac rac", FakeOcr())


def test_pdf_co_mat_khau_bao_loi_trich_xuat():
    doc = pymupdf.open(stream=make_pdf(["bi mat"]), filetype="pdf")
    data = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="u", owner_pw="o")
    with pytest.raises(ExtractionError, match="mật khẩu"):
        extract_pdf(data, FakeOcr())


def test_docx_hong_bao_loi_trich_xuat():
    with pytest.raises(ExtractionError):
        extract_docx(b"PK\x03\x04 khong phai docx")


# --- Pipeline + tiến độ job:{jobId} --------------------------------------------------------------


@dataclass
class FakeRepo:
    docs: dict[UUID, DocumentRef] = field(default_factory=dict)
    status: dict[UUID, str] = field(default_factory=dict)
    page_count: dict[UUID, int] = field(default_factory=dict)
    errors: dict[UUID, str] = field(default_factory=dict)

    def get(self, document_id: UUID) -> DocumentRef | None:
        return self.docs.get(document_id)

    def mark_parsing(self, document_id: UUID) -> bool:
        if self.status.get(document_id) == DocumentStatus.PARSED:
            return False
        self.status[document_id] = DocumentStatus.PARSING
        return True

    def mark_parsed(self, document_id: UUID, page_count: int) -> None:
        self.status[document_id] = DocumentStatus.PARSED
        self.page_count[document_id] = page_count

    def mark_failed(self, document_id: UUID, message: str) -> None:
        self.status[document_id] = DocumentStatus.FAILED
        self.errors[document_id] = message


@pytest.fixture
def env():
    storage = InMemoryStorage("whybi")
    repo = FakeRepo()
    progress = InMemoryJobProgress()

    def add(data: bytes, ext: str) -> DocumentRef:
        doc_id, class_id = uuid4(), uuid4()
        url = storage.put(f"syllabi/{class_id}/{doc_id}.{ext}", data, "application/octet-stream")
        ref = DocumentRef(id=doc_id, class_id=class_id, file_url=url, file_type=ext)
        repo.docs[doc_id] = ref
        return ref

    return storage, repo, progress, add


def _steps(progress: InMemoryJobProgress, job_id: str) -> list[JobProgress]:
    out = []
    for channel, event, payload in progress.events:
        assert channel == f"job:{job_id}"
        assert event == "job.progress"
        out.append(JobProgress.model_validate(payload))
    return out


def test_pipeline_pdf_luu_trang_va_bao_tien_do(env):
    storage, repo, progress, add = env
    ref = add(make_pdf(["Trang 1 mang", "Trang 2 danh sach"]), "pdf")
    job_id = str(uuid4())

    pages = SyllabusPreprocessor(repo, storage, progress, FakeOcr()).run(ref.id, job_id)

    assert len(pages) == 2
    assert repo.status[ref.id] == DocumentStatus.PARSED
    assert repo.page_count[ref.id] == 2
    saved = json.loads(storage.objects[pages_key(ref.class_id, ref.id)])
    assert [p["number"] for p in saved["pages"]] == [1, 2]
    assert "danh sach" in saved["pages"][1]["text"]
    steps = _steps(progress, job_id)
    percents = [s.percent for s in steps]
    assert percents == sorted(percents) and percents[0] < 100 and percents[-1] == 100
    assert steps[-1].step == "DONE"
    assert any(s.step == "EXTRACTING" for s in steps)


def test_pipeline_ban_quet_bao_buoc_ocr(env):
    storage, repo, progress, add = env
    ref = add(make_pdf_mixed([("scan", "Trang quet")]), "pdf")
    job_id = str(uuid4())
    pages = SyllabusPreprocessor(repo, storage, progress, FakeOcr()).run(ref.id, job_id)
    assert pages[0].ocr is True
    assert "OCR" in [s.step for s in _steps(progress, job_id)]
    assert repo.status[ref.id] == DocumentStatus.PARSED


def test_pipeline_docx(env):
    storage, repo, progress, add = env
    ref = add(make_docx([("p", "Mot"), ("break", ""), ("p", "Hai")]), "docx")
    pages = SyllabusPreprocessor(repo, storage, progress, FakeOcr()).run(ref.id, "j1")
    assert [p.text.strip() for p in pages] == ["Mot", "Hai"]
    assert repo.page_count[ref.id] == 2


def test_pipeline_payload_camelcase_dung_hop_dong(env):
    storage, repo, progress, add = env
    ref = add(make_pdf(["x" * 60]), "pdf")
    SyllabusPreprocessor(repo, storage, progress, FakeOcr()).run(ref.id, "j2")
    for _, _, payload in progress.events:
        assert set(payload) == {"percent", "step"}
        assert 0 <= payload["percent"] <= 100


def test_pipeline_tep_hong_chuyen_failed_khong_nem_loi(env):
    storage, repo, progress, add = env
    ref = add(b"%PDF-1.7\nrac", "pdf")
    assert SyllabusPreprocessor(repo, storage, progress, FakeOcr()).run(ref.id, "j3") == []
    assert repo.status[ref.id] == DocumentStatus.FAILED
    assert repo.errors[ref.id]
    assert _steps(progress, "j3")[-1].step == "FAILED"


def test_pipeline_khong_trich_duoc_chu_nao_la_failed(env):
    storage, repo, progress, add = env
    ref = add(make_pdf_mixed([("blank", ""), ("blank", "")]), "pdf")
    SyllabusPreprocessor(repo, storage, progress, FakeOcr()).run(ref.id, "j4")
    assert repo.status[ref.id] == DocumentStatus.FAILED
    assert "chữ" in repo.errors[ref.id]


def test_pipeline_kho_luu_tru_loi_la_failed(env):
    storage, repo, progress, add = env
    ref = add(make_pdf(["abc"]), "pdf")

    class Broken(InMemoryStorage):
        def get(self, url: str) -> bytes:
            raise StorageUnavailable("mất kết nối")

    SyllabusPreprocessor(repo, Broken("whybi"), progress, FakeOcr()).run(ref.id, "j5")
    assert repo.status[ref.id] == DocumentStatus.FAILED
    assert "kho" in repo.errors[ref.id]


def test_pipeline_chua_cai_tesseract_la_failed(env):
    storage, repo, progress, add = env
    ref = add(make_pdf_mixed([("scan", "x")]), "pdf")
    ocr = FakeOcr(error=OcrError("tesseract is not installed"))
    SyllabusPreprocessor(repo, storage, progress, ocr).run(ref.id, "j6")
    assert repo.status[ref.id] == DocumentStatus.FAILED
    assert "OCR" in repo.errors[ref.id]


@pytest.mark.parametrize("raised", ["not_found", "tess_error", "timeout"])
def test_tesseract_doi_loi_thanh_ocr_error(monkeypatch, raised):
    import pytesseract

    errors = {
        "not_found": pytesseract.TesseractNotFoundError(),
        "tess_error": pytesseract.TesseractError(1, "Failed loading language 'vie'"),
        "timeout": RuntimeError("Tesseract process timeout"),
    }

    def boom(*a, **k):
        raise errors[raised]

    monkeypatch.setattr(pytesseract, "image_to_string", boom)
    with pytest.raises(OcrError):
        documents.TesseractOcr().image_to_text(scanned_page_png("x"))


def test_pipeline_loi_bat_ngo_van_danh_dau_failed_roi_nem_lai(env):
    storage, repo, progress, add = env
    ref = add(make_pdf_mixed([("scan", "x")]), "pdf")
    with pytest.raises(RuntimeError):
        SyllabusPreprocessor(repo, storage, progress, FakeOcr(error=RuntimeError("bùm"))).run(ref.id, "j7")
    assert repo.status[ref.id] == DocumentStatus.FAILED
    assert _steps(progress, "j7")[-1].step == "FAILED"


def test_pipeline_khong_co_tai_lieu_thi_bo_qua(env):
    storage, repo, progress, _ = env
    assert SyllabusPreprocessor(repo, storage, progress, FakeOcr()).run(uuid4(), "j8") == []
    assert _steps(progress, "j8")[-1].step == "FAILED"


# --- Phát tiến độ lên Redis ----------------------------------------------------------------------


class FakeRedis:
    def __init__(self, error: Exception | None = None):
        self.sent: list[tuple[str, str]] = []
        self.error = error

    def publish(self, channel: str, data: str) -> int:
        if self.error:
            raise self.error
        self.sent.append((channel, data))
        return 1


def test_redis_progress_phat_dung_kenh_va_phong_bi():
    r = FakeRedis()
    RedisJobProgress(client=r).report("abc", 40, "EXTRACTING")
    channel, data = r.sent[0]
    # RedisRelay của cổng WebSocket chỉ nghe mẫu "ws:*" rồi bỏ tiền tố – thiếu tiền tố thì GV không nhận được gì
    assert channel == gateway.REDIS_PREFIX + "job:abc"
    assert json.loads(data) == {
        "channel": "job:abc",
        "event": "job.progress",
        "payload": {"percent": 40, "step": "EXTRACTING"},
    }


def test_redis_progress_redis_rot_khong_lam_hong_job(caplog):
    import redis

    RedisJobProgress(client=FakeRedis(error=redis.ConnectionError("rớt"))).report("abc", 10, "DOWNLOADING")
    assert "job:abc" in caplog.text


# --- Tác vụ Celery --------------------------------------------------------------------------------


def test_task_celery_goi_pipeline(monkeypatch):
    calls = []

    class P:
        def run(self, document_id, job_id):
            calls.append((document_id, job_id))
            return []

    class Ctx:
        def __enter__(self):
            return P()

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(documents, "open_preprocessor", lambda: Ctx())
    doc_id = uuid4()
    documents.process_syllabus(str(doc_id), "job-1")
    assert calls == [(doc_id, "job-1")]


def test_task_nam_tren_hang_doi_documents():
    from app.workers.celery_app import celery

    route = celery.amqp.router.route({}, "app.workers.documents.process_syllabus")
    assert route["queue"].name == "documents"


# --- Hồi quy PR #110 -----------------------------------------------------------------------------


def _save_docx(d) -> bytes:
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def test_docx_ngat_cung_van_co_hieu_luc_khi_co_rendered_o_noi_khac():
    d = docx.Document()
    d.add_paragraph("Mot")
    r = d.add_paragraph("Hai").runs[0]
    r._r.insert(0, OxmlElement("w:lastRenderedPageBreak"))
    d.add_page_break()
    d.add_paragraph("Ba")
    assert [p.text.strip() for p in extract_docx(_save_docx(d))] == ["Mot", "Hai", "Ba"]


@pytest.mark.parametrize("rendered", [False, True])
def test_docx_ngat_trang_trong_bang_giu_dung_trang(rendered):
    d = docx.Document()
    d.add_paragraph("Truoc")
    p = d.add_table(rows=1, cols=1).cell(0, 0).paragraphs[0]
    p.add_run("O mot")
    if rendered:
        p.add_run()._r.append(OxmlElement("w:lastRenderedPageBreak"))
    else:
        p.add_run().add_break(WD_BREAK.PAGE)
    p.add_run("O hai")
    d.add_paragraph("Sau")
    pages = extract_docx(_save_docx(d))
    assert [p.number for p in pages] == [1, 2]
    assert "O mot" in pages[0].text and "O hai" not in pages[0].text
    assert "O hai" in pages[1].text and "Sau" in pages[1].text


def test_docx_page_break_before_dau_tai_lieu_khong_sinh_trang_trang():
    d = docx.Document()
    p = d.add_paragraph("Mo dau")
    p.paragraph_format.page_break_before = True
    assert [p.text.strip() for p in extract_docx(_save_docx(d))] == ["Mo dau"]


def test_docx_ngat_trang_ke_thua_tu_style():
    d = docx.Document()
    d.add_paragraph("Mot")
    d.styles["Heading 1"].paragraph_format.page_break_before = True
    d.add_heading("Hai", 1)
    assert [p.text.strip() for p in extract_docx(_save_docx(d))] == ["Mot", "Hai"]


def test_docx_giu_trang_rong_duoc_tao_bang_ngat_cung_cuoi_tep():
    pages = extract_docx(make_docx([("p", "Mot"), ("break", ""), ("break", "")]))
    assert [p.number for p in pages] == [1, 2, 3]
    assert [p.text.strip() for p in pages] == ["Mot", "", ""]


def test_pipeline_khong_nuot_loi_khi_khong_ghi_duoc_failed(env, monkeypatch):
    storage, repo, progress, add = env
    ref = add(b"%PDF-1.7\nrac", "pdf")
    monkeypatch.setattr(repo, "mark_failed", Mock(side_effect=RuntimeError("database unavailable")))
    with pytest.raises(RuntimeError, match="database unavailable"):
        SyllabusPreprocessor(repo, storage, progress, FakeOcr()).run(ref.id, "db-failure")
    assert _steps(progress, "db-failure")[-1].step == "FAILED"


@pytest.fixture
def processing_repo():
    """SQLite chỉ cho bảng tài liệu: test trạng thái thật, không cần stack/Postgres."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.models.users import SyllabusDocument

    engine = create_engine("sqlite://")
    SyllabusDocument.__table__.create(engine)
    with Session(engine) as db:
        doc = SyllabusDocument(
            id=uuid4(), class_id=uuid4(), uploaded_by=uuid4(), file_url="s3://whybi/input.pdf", file_type="pdf"
        )
        db.add(doc)
        db.commit()
        yield SyllabusProcessingRepo(db), doc
    engine.dispose()


def test_job_giao_lai_sau_parsed_khong_doc_ghi_lai_tai_lieu(processing_repo, monkeypatch):
    repo, doc = processing_repo
    storage, progress = InMemoryStorage("whybi"), InMemoryJobProgress()
    storage.put("input.pdf", make_pdf(["Noi dung"]), "application/pdf")
    pre = SyllabusPreprocessor(repo, storage, progress, FakeOcr())
    assert len(pre.run(doc.id, "redelivery")) == 1
    saved = dict(storage.objects)
    progress.events.clear()
    get = Mock(side_effect=StorageUnavailable("storage down on redelivery"))
    put = Mock(side_effect=StorageUnavailable("must not rewrite"))
    monkeypatch.setattr(storage, "get", get)
    monkeypatch.setattr(storage, "put", put)
    assert pre.run(doc.id, "redelivery") == []
    get.assert_not_called()
    put.assert_not_called()
    repo.db.refresh(doc)
    assert (doc.status, doc.page_count, doc.error_message) == (DocumentStatus.PARSED, 1, None)
    assert storage.objects == saved
    assert [s.step for s in _steps(progress, "redelivery")] == ["DONE"]


def test_mark_failed_khong_ghi_de_tai_lieu_da_parsed(processing_repo):
    repo, doc = processing_repo
    repo.mark_parsed(doc.id, 3)
    repo.mark_failed(doc.id, "late failure")
    repo.db.refresh(doc)
    assert (doc.status, doc.page_count, doc.error_message) == (DocumentStatus.PARSED, 3, None)


def test_loi_commit_parsed_rollback_roi_ghi_failed(processing_repo, monkeypatch):
    from sqlalchemy.exc import OperationalError

    repo, doc = processing_repo
    storage, progress = InMemoryStorage("whybi"), InMemoryJobProgress()
    storage.put("input.pdf", make_pdf(["Noi dung"]), "application/pdf")
    commit = repo.db.commit
    calls = 0

    def fail_second_commit():
        nonlocal calls
        calls += 1
        if calls == 2:
            repo.db.flush()
            raise OperationalError("COMMIT", {}, RuntimeError("database disconnected"))
        commit()

    monkeypatch.setattr(repo.db, "commit", fail_second_commit)
    with pytest.raises(OperationalError):
        SyllabusPreprocessor(repo, storage, progress, FakeOcr()).run(doc.id, "commit-failure")
    repo.db.refresh(doc)
    assert doc.status == DocumentStatus.FAILED and doc.page_count is None and doc.error_message
    assert _steps(progress, "commit-failure")[-1].step == "FAILED"
