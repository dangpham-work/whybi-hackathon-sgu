"""Hàng đợi `documents` – tiền xử lý giáo trình và sinh cây (UC06, Hình 4.16). Chủ: Đăng (C1-09…C1-11).

C1-09 (mục 6.1.1): tải tệp từ kho đối tượng → bóc chữ theo trang (PyMuPDF cho PDF, python-docx cho DOCX)
→ trang PDF gần như không có chữ mà có ảnh ⇒ coi là bản quét, OCR Tesseract `vie+eng` → lưu JSON các trang
vào `syllabi/{classId}/{docId}.pages.json` (C1-10 đọc lại) → syllabus_documents PARSED + page_count.
Tiến độ phát `job.progress {percent, step}` (`JobProgress`) trên kênh `job:{jobId}` (Bảng 5.11).

Chia đoạn ~500 token + embedding → document_chunks thuộc C1-11 (RAG); trích khái niệm thuộc C1-10.
"""

import io
import json
import logging
import zipfile
from collections import Counter
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol
from uuid import UUID

import docx
import pymupdf
import pytesseract
from docx.opc.exceptions import PackageNotFoundError
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.models.enums import DocumentStatus
from app.models.schemas.mastery import JobProgress
from app.realtime.gateway import REDIS_PREFIX, channel_job
from app.services.retrieval import RetrievalService
from app.services.storage import ObjectStorage, StorageUnavailable
from app.services.syllabus import DocumentRef, pages_key, sibling_url, toc_key
from app.workers.celery_app import celery

log = logging.getLogger(__name__)

EVENT_JOB_PROGRESS = "job.progress"
# Trang có ít hơn ngần này ký tự (bỏ khoảng trắng) mà có ảnh ⇒ coi là trang quét, chạy OCR.
SCAN_MIN_CHARS = 40
OCR_DPI = 300
OCR_LANG = "vie+eng"  # giáo trình CNTT lẫn thuật ngữ tiếng Anh
OCR_TIMEOUT_S = 120
FILL_LOCK_TTL_S = 900  # khóa sinh rubric bù theo lớp: hết hạn sau 15 phút phòng worker chết giữa chừng
HEADING_SIZE_RATIO = 1.2  # cỡ chữ ≥ 1,2 × cỡ thân bài ⇒ tiêu đề
HEADING_MAX_CHARS = 150


class ExtractionError(Exception):
    """Tệp không đọc được (hỏng, có mật khẩu, không có trang…). Thông điệp hiển thị cho GV."""


@dataclass
class Page:
    number: int  # bắt đầu từ 1 – dùng cho trích dẫn trang (rubric, RAG)
    text: str
    ocr: bool = False
    headings: list[str] = field(default_factory=list)


# --- OCR ------------------------------------------------------------------------------------------


class OcrError(Exception):
    """OCR không chạy được: thiếu binary / gói ngôn ngữ, Tesseract lỗi hoặc quá thời gian."""


class OcrEngine(Protocol):
    def image_to_text(self, png: bytes) -> str: ...


class TesseractOcr:
    """Cần binary `tesseract` + gói `vie` (Dockerfile backend đã cài)."""

    def __init__(self, lang: str = OCR_LANG, timeout: int = OCR_TIMEOUT_S) -> None:
        self.lang = lang
        self.timeout = timeout

    def image_to_text(self, png: bytes) -> str:
        from PIL import Image

        with Image.open(io.BytesIO(png)) as img:
            try:
                return pytesseract.image_to_string(img, lang=self.lang, timeout=self.timeout)
            except (pytesseract.TesseractNotFoundError, pytesseract.TesseractError) as exc:
                raise OcrError(str(exc)) from exc
            except RuntimeError as exc:  # pytesseract báo quá thời gian bằng RuntimeError
                if "timeout" in str(exc).lower():
                    raise OcrError(str(exc)) from exc
                raise


# --- PDF ------------------------------------------------------------------------------------------

PageCallback = Callable[[int, int, bool], None]  # (trang thứ i, tổng số trang, có OCR)


def _visible_chars(text: str) -> int:
    return sum(1 for ch in text if not ch.isspace())


def _pdf_lines(page: Any) -> list[tuple[str, float]]:
    """Các dòng chữ của trang kèm cỡ chữ lớn nhất trong dòng."""
    out = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            spans = [s for s in line["spans"] if s["text"].strip()]
            if spans:
                out.append(("".join(s["text"] for s in spans).strip(), max(s["size"] for s in spans)))
    return out


def extract_pdf(data: bytes, ocr: OcrEngine, on_page: PageCallback | None = None) -> list[Page]:
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except (pymupdf.FileDataError, pymupdf.EmptyFileError) as exc:
        raise ExtractionError("Tệp PDF bị hỏng, không đọc được") from exc
    with doc:
        if doc.needs_pass:
            raise ExtractionError("PDF có mật khẩu – hãy gỡ mật khẩu rồi tải lại")
        if doc.page_count == 0:
            raise ExtractionError("Tệp PDF không có trang nào")

        pages: list[Page] = []
        lines_by_page: list[list[tuple[str, float]]] = []
        n = doc.page_count
        for i, page in enumerate(doc, start=1):
            text = page.get_text("text")
            lines: list[tuple[str, float]] = []
            is_scan = _visible_chars(text) < SCAN_MIN_CHARS and bool(page.get_images())
            if is_scan:
                png = page.get_pixmap(dpi=OCR_DPI, colorspace=pymupdf.csGRAY).tobytes("png")
                text = ocr.image_to_text(png)
            else:
                lines = _pdf_lines(page)
            pages.append(Page(number=i, text=text, ocr=is_scan))
            lines_by_page.append(lines)
            if on_page:
                on_page(i, n, is_scan)

    _mark_pdf_headings(pages, lines_by_page)
    return pages


def _mark_pdf_headings(pages: list[Page], lines_by_page: list[list[tuple[str, float]]]) -> None:
    """Cỡ thân bài = cỡ chữ chiếm nhiều ký tự nhất toàn tài liệu; dòng lớn hơn hẳn ⇒ tiêu đề (mục 6.1.1)."""
    weight: Counter[float] = Counter()
    for lines in lines_by_page:
        for text, size in lines:
            weight[round(size, 1)] += len(text)
    if not weight:
        return
    body = weight.most_common(1)[0][0]
    for page, lines in zip(pages, lines_by_page, strict=True):
        page.headings = [t for t, s in lines if s >= body * HEADING_SIZE_RATIO and len(t) <= HEADING_MAX_CHARS]


# --- DOCX -----------------------------------------------------------------------------------------

_W_T, _W_TAB, _W_BR, _W_CR = qn("w:t"), qn("w:tab"), qn("w:br"), qn("w:cr")
_W_RENDERED = qn("w:lastRenderedPageBreak")
_W_TYPE = qn("w:type")


class _DocxPager:
    """Gom chữ theo các dấu ngắt trang. Dấu Word dàn trang ngay sau ngắt cứng chỉ tính một lần;
    dấu ngắt đã dàn ở nơi khác không vô hiệu hóa ngắt cứng của cả tài liệu."""

    def __init__(self, rendered: bool) -> None:
        self.rendered = rendered
        self.pages: list[Page] = []
        self._lines: list[str] = []
        self._headings: list[str] = []
        self._after_hard_break = False

    def _flush(self) -> None:
        self.pages.append(Page(number=len(self.pages) + 1, text="\n".join(self._lines), headings=self._headings))
        self._lines, self._headings = [], []

    def new_page(self) -> None:
        self._flush()

    def paragraph(self, p: Paragraph, separator: str | None = None) -> None:
        before = p.paragraph_format.page_break_before
        style = p.style
        while before is None and style is not None:
            before = style.paragraph_format.page_break_before
            style = style.base_style
        if before and any(line.strip() for line in self._lines):
            self.new_page()
            self._after_hard_break = True
        heading = p.style is not None and p.style.name.startswith(("Heading", "Title"))

        def append(text: str) -> None:
            nonlocal separator
            if separator and self._lines:
                self._lines[-1] += separator + text
            else:
                self._lines.append(text)
            separator = None
            if heading and text.strip():
                self._headings.append(text.strip())

        buf: list[str] = []
        for el in p._p.iter():
            tag = el.tag
            if tag == _W_T:
                buf.append(el.text or "")
                if (el.text or "").strip():
                    self._after_hard_break = False
            elif tag == _W_TAB:
                buf.append("\t")
            elif tag == _W_CR:
                buf.append("\n")
            elif tag == _W_BR:
                if el.get(_W_TYPE) == "page":
                    append("".join(buf))
                    buf = []
                    self.new_page()
                    self._after_hard_break = True
                else:
                    buf.append("\n")
            elif tag == _W_RENDERED and self.rendered:
                append("".join(buf))
                buf = []
                if not self._after_hard_break:
                    self.new_page()
                self._after_hard_break = False
        append("".join(buf))

    def table(self, t: Table) -> None:
        for row in t.rows:
            seen = set()
            for cell in row.cells:  # ô gộp lặp lại cùng một w:tc
                if cell._tc in seen:
                    continue
                separator = " | " if seen else None
                seen.add(cell._tc)
                for block in cell.iter_inner_content():
                    if isinstance(block, Paragraph):
                        self.paragraph(block, separator=separator)
                    else:
                        self.table(block)
                    separator = None

    def finish(self) -> list[Page]:
        self._flush()
        return self.pages


def extract_docx(data: bytes) -> list[Page]:
    try:
        d = docx.Document(io.BytesIO(data))
    # XML hỏng: lxml.etree.XMLSyntaxError kế thừa SyntaxError – bắt qua lớp chuẩn, không import lxml trực tiếp
    except (PackageNotFoundError, zipfile.BadZipFile, KeyError, ValueError, SyntaxError) as exc:
        raise ExtractionError("Tệp DOCX bị hỏng, không đọc được") from exc
    body = d.element.body
    pager = _DocxPager(rendered=bool(body.findall(".//" + _W_RENDERED)))
    for block in d.iter_inner_content():
        if isinstance(block, Paragraph):
            pager.paragraph(block)
        else:
            pager.table(block)
    return pager.finish()


# --- Tiến độ trên kênh job:{jobId} ---------------------------------------------------------------


class JobCancelled(Exception):
    """Tiến trình bị người dùng hủy giữa chừng."""


class JobProgressSink(Protocol):
    def report(self, job_id: str, percent: int, step: str) -> None: ...

    def emit(self, job_id: str, event: str, payload: dict[str, Any]) -> None: ...

    def is_cancelled(self, job_id: str) -> bool: ...


def _envelope(job_id: str, percent: int, step: str) -> dict[str, Any]:
    payload = JobProgress(percent=percent, step=step).model_dump(by_alias=True, mode="json")
    return {"channel": channel_job(job_id), "event": EVENT_JOB_PROGRESS, "payload": payload}


class InMemoryJobProgress:
    """Cho test: ghi lại (channel, event, payload)."""

    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict[str, Any]]] = []
        self.cancelled: set[str] = set()

    def report(self, job_id: str, percent: int, step: str) -> None:
        e = _envelope(job_id, percent, step)
        self.events.append((e["channel"], e["event"], e["payload"]))

    def emit(self, job_id: str, event: str, payload: dict[str, Any]) -> None:
        self.events.append((channel_job(job_id), event, payload))

    def is_cancelled(self, job_id: str) -> bool:
        return job_id in self.cancelled

    def cancel(self, job_id: str) -> None:
        self.cancelled.add(job_id)
        self.report(job_id, 0, "CANCELLED")

    def uncancel(self, job_id: str) -> None:
        self.cancelled.discard(job_id)


class RedisJobProgress:
    """PUBLISH lên kênh Redis `ws:job:{jobId}` (tiền tố `gateway.REDIS_PREFIX` – RedisRelay của cổng WebSocket
    C2-13 nghe `ws:*` rồi giao cho GV đang nghe `job:{jobId}`), thân tin đúng dạng client nhận
    `{channel, event, payload}`.
    Không gọi thẳng `gateway.broadcast` để nhận client Redis tiêm vào (test) và nuốt lỗi Redis:
    tiến độ là phụ, Redis rớt thì ghi log, không làm hỏng job."""

    def __init__(self, client: Any = None) -> None:
        self._client = client

    def _redis(self) -> Any:
        if self._client is None:
            import redis

            from app.core.config import get_settings

            self._client = redis.Redis.from_url(get_settings().redis_url, socket_timeout=2, socket_connect_timeout=2)
        return self._client

    def report(self, job_id: str, percent: int, step: str) -> None:
        e = _envelope(job_id, percent, step)
        self._publish(e)

    def emit(self, job_id: str, event: str, payload: dict[str, Any]) -> None:
        self._publish({"channel": channel_job(job_id), "event": event, "payload": payload})

    def is_cancelled(self, job_id: str) -> bool:
        try:
            return bool(self._redis().exists(f"job:{job_id}:cancelled"))
        except Exception:
            return False

    def cancel(self, job_id: str) -> None:
        try:
            r = self._redis()
            r.set(f"job:{job_id}:cancelled", "1", ex=3600)
            self.report(job_id, 0, "CANCELLED")
        except Exception as exc:
            log.warning("không ghi được cờ hủy cho job %s: %s", job_id, exc)

    def uncancel(self, job_id: str) -> None:
        """Xóa cờ hủy cũ trước khi xếp lại job cùng id (job_id = documentId), kẻo job mới bị hủy ngay."""
        try:
            self._redis().delete(f"job:{job_id}:cancelled")
        except Exception as exc:
            log.warning("không xóa được cờ hủy của job %s: %s", job_id, exc)

    def lock_fill(self, class_id: Any) -> bool:
        """Khóa 'đang sinh rubric bù' theo lớp (hết hạn sau 15 phút phòng worker chết). Redis lỗi ⇒ cho qua."""
        try:
            return bool(self._redis().set(f"job:fill:{class_id}", "1", nx=True, ex=FILL_LOCK_TTL_S))
        except Exception as exc:
            log.warning("không đặt được khóa sinh rubric lớp %s: %s", class_id, exc)
            return True

    def unlock_fill(self, class_id: Any) -> None:
        try:
            self._redis().delete(f"job:fill:{class_id}")
        except Exception as exc:
            log.warning("không nhả được khóa sinh rubric lớp %s: %s", class_id, exc)

    def _publish(self, e: dict[str, Any]) -> None:
        import redis

        try:
            self._redis().publish(REDIS_PREFIX + e["channel"], json.dumps(e, ensure_ascii=False))
        except (redis.RedisError, OSError) as exc:
            log.warning("không phát được sự kiện %s (%s): %s", e["channel"], e["event"], exc)


class _Progress:
    """Giữ phần trăm không giảm; nhớ mức cuối để báo FAILED hoặc CANCELLED đúng chỗ thanh tiến độ dừng."""

    def __init__(self, sink: JobProgressSink, job_id: str) -> None:
        self.sink, self.job_id, self.percent = sink, job_id, 0

    def __call__(self, percent: int, step: str) -> None:
        if self.sink.is_cancelled(self.job_id):
            raise JobCancelled(f"job {self.job_id} đã bị hủy bởi người dùng")
        self.percent = max(self.percent, min(100, percent))
        self.sink.report(self.job_id, self.percent, step)

    def fail(self) -> None:
        self.sink.report(self.job_id, self.percent, "FAILED")

    def cancel(self) -> None:
        self.sink.report(self.job_id, self.percent, "CANCELLED")


# --- Pipeline -------------------------------------------------------------------------------------


class DocumentRepo(Protocol):
    def get(self, document_id: UUID) -> DocumentRef | None: ...
    def mark_parsing(self, document_id: UUID) -> bool: ...
    def mark_parsed(self, document_id: UUID, page_count: int) -> None: ...
    def mark_failed(self, document_id: UUID, message: str) -> None: ...


MSG_STORAGE = "Không đọc / ghi được tệp trong kho lưu trữ – hãy thử tải lại"
MSG_OCR = "Không chạy được OCR cho bản quét (máy chủ thiếu Tesseract hoặc gói tiếng Việt)"
MSG_NO_TEXT = "Không trích được chữ nào từ tài liệu"
MSG_UNEXPECTED = "Lỗi không mong đợi khi xử lý tài liệu – hãy thử tải lại"


class SyllabusPreprocessor:
    """Bước tiến độ: DOWNLOADING 5 → EXTRACTING / OCR 10…90 (theo trang) → SAVING 95 → DONE 100; lỗi → FAILED."""

    def __init__(self, repo: DocumentRepo, storage: ObjectStorage, progress: JobProgressSink, ocr: OcrEngine) -> None:
        self.repo, self.storage, self.progress, self.ocr = repo, storage, progress, ocr

    def run(self, document_id: UUID, job_id: str) -> list[Page]:
        prog = _Progress(self.progress, job_id)
        ref = self.repo.get(document_id)
        if ref is None:
            log.error("job %s: không có tài liệu %s", job_id, document_id)
            prog.fail()
            return []
        try:
            if self.repo.mark_parsing(ref.id) is False:
                # acks_late: worker có thể chết sau commit PARSED nhưng trước ACK.
                prog(100, "DONE")
                return []
            prog(5, "DOWNLOADING")
            data = self.storage.get(ref.file_url)
            prog(10, "EXTRACTING")
            pages = self._extract(ref.file_type, data, prog)
            if not any(p.text.strip() for p in pages):
                raise ExtractionError(MSG_NO_TEXT)
            prog(95, "SAVING")
            body = json.dumps({"documentId": str(ref.id), "pages": [asdict(p) for p in pages]}, ensure_ascii=False)
            self.storage.put(pages_key(ref.class_id, ref.id), body.encode(), "application/json")
            self.repo.mark_parsed(ref.id, len(pages))
            prog(100, "DONE")
            log.info("job %s: tài liệu %s xong %d trang (%d trang OCR)", job_id, ref.id, len(pages), _n_ocr(pages))
            return pages
        except JobCancelled:
            log.info("job %s: người dùng đã hủy bóc chữ tài liệu %s", job_id, ref.id)
            self._cancel(ref, prog)
            return []
        except ExtractionError as exc:
            log.warning("job %s: tài liệu %s không bóc được: %s", job_id, ref.id, exc)
            self._fail(ref, prog, str(exc))
        except StorageUnavailable:
            log.exception("job %s: lỗi kho lưu trữ với %s", job_id, ref.file_url)
            self._fail(ref, prog, MSG_STORAGE)
        except OcrError:
            log.exception("job %s: OCR lỗi với tài liệu %s", job_id, ref.id)
            self._fail(ref, prog, MSG_OCR)
        except Exception:
            log.exception("job %s: lỗi không mong đợi với tài liệu %s", job_id, ref.id)
            self._fail(ref, prog, MSG_UNEXPECTED)
            raise
        return []

    def _extract(self, file_type: str, data: bytes, prog: _Progress) -> list[Page]:
        if file_type == "pdf":

            def on_page(i: int, n: int, ocr: bool) -> None:
                prog(10 + 80 * i // n, "OCR" if ocr else "EXTRACTING")

            return extract_pdf(data, self.ocr, on_page)
        if file_type == "docx":
            pages = extract_docx(data)
            prog(90, "EXTRACTING")
            return pages
        raise ExtractionError(f"Không hỗ trợ định dạng {file_type!r}")

    def _fail(self, ref: DocumentRef, prog: _Progress, message: str) -> None:
        try:
            self.repo.mark_failed(ref.id, message)
        except Exception:
            log.exception("không ghi được trạng thái %s cho tài liệu %s", DocumentStatus.FAILED, ref.id)
            raise
        finally:
            prog.fail()

    def _cancel(self, ref: DocumentRef, prog: _Progress, message: str = "Đã hủy theo yêu cầu") -> None:
        try:
            self.repo.mark_failed(ref.id, message)
        except Exception:
            log.exception("không ghi được trạng thái FAILED khi hủy tài liệu %s", ref.id)
        finally:
            prog.cancel()


def _n_ocr(pages: list[Page]) -> int:
    return sum(1 for p in pages if p.ocr)


# --- Tác vụ Celery --------------------------------------------------------------------------------


@contextmanager
def open_preprocessor() -> Iterator[SyllabusPreprocessor]:
    from app.db.session import SessionLocal
    from app.services.storage import default_storage
    from app.services.syllabus import SyllabusProcessingRepo

    db = SessionLocal()
    try:
        yield SyllabusPreprocessor(SyllabusProcessingRepo(db), default_storage(), RedisJobProgress(), TesseractOcr())
    finally:
        db.close()


EVENT_TOC_READY = "syllabus.toc_ready"
STEP_AWAITING = "AWAITING_SELECTION"


def _chars_between(pages: list[Page], start: int | None, end: int | None, skip: set[int]) -> int:
    """Ký tự (không tính khoảng trắng) của các trang start–end, bỏ trang mục lục; 0 khi chưa biết trang."""
    if start is None or end is None:
        return 0
    return sum(_visible_chars(p.text) for p in pages if start <= p.number <= end and p.number not in skip)


class TocStep:
    """Sau khi bóc chữ, TRƯỚC khi tốn token dựng cây: dò mục lục (Python, 0 token), ước cỡ, nếu lớn thì nhờ AI viết
    cảnh báo từ danh sách mục lục và lưu `toc.json`. Trả True ⇒ dừng, chờ GV chọn chương (POST …/build-tree).
    Lỗi bất kỳ chỉ ghi log và coi như không có cổng: dựng cây như trước, không làm hỏng job."""

    def __init__(self, storage: ObjectStorage, progress: JobProgressSink, gateway: Any) -> None:
        self.storage, self.progress, self.gw = storage, progress, gateway

    def run(self, ref: DocumentRef, job_id: str, pages: list[Page]) -> bool:
        try:
            return self._run(ref, job_id, pages)
        except Exception:
            log.exception("job %s: bước mục lục lỗi, bỏ qua và dựng cây như thường", job_id)
            return False

    def _bookmarks(self, ref: DocumentRef) -> list[tuple[int, str, int]]:
        if ref.file_type != "pdf":
            return []
        try:
            with pymupdf.open(stream=self.storage.get(ref.file_url), filetype="pdf") as doc:
                return [(lvl, title, page) for lvl, title, page in (x[:3] for x in doc.get_toc())]
        except Exception:  # noqa: BLE001 – bookmark chỉ là đường tắt, không có thì dò trang mục lục
            return []

    def _run(self, ref: DocumentRef, job_id: str, pages: list[Page]) -> bool:
        from app.ai.agents.toc_advisor import advise, classify_chapters
        from app.core.config import get_settings
        from app.models.schemas.toc import TocAdvice, TocChapter, TocReport
        from app.services.syllabus_toc import CHARS_PER_CHUNK, DETAIL_CAPS, NODES_PER_CHUNK, estimate_size, find_toc

        cfg = get_settings()
        if self.progress.is_cancelled(job_id):
            return False
        res = find_toc([asdict(p) for p in pages], self._bookmarks(ref))
        if self.progress.is_cancelled(job_id):
            return False
        if res.ambiguous and res.entries:
            classify_chapters(
                self.gw, res
            )  # không nhận ra chương bằng từ khóa ⇒ AI nhỏ bỏ tên sách / tổng quan / phụ lục
        skip = set(res.toc_pages)
        chars = sum(_visible_chars(p.text) for p in pages if p.number not in skip)  # trang mục lục sẽ bị loại
        est = estimate_size(chars, len(res.entries), cfg.toc_warn_nodes, cfg.toc_max_nodes)
        if est.level == "OK":
            advice, by_ai = TocAdvice(message="Giáo trình cỡ vừa, có thể dựng cây ngay."), False
        else:
            advice, by_ai = advise(self.gw, res, est, cfg.toc_warn_nodes)
        gated = cfg.toc_gate_enabled and est.level != "OK"
        report = TocReport(
            document_id=str(ref.id),
            source=res.source,
            total_pages=res.total_pages,
            total_chars=chars,
            offset=res.offset,
            toc_pages=res.toc_pages,
            level=est.level,
            est_nodes=est.nodes,
            est_calls=est.llm_calls,
            chars_per_chunk=CHARS_PER_CHUNK,
            nodes_per_chunk=dict(NODES_PER_CHUNK),
            detail_caps=dict(DETAIL_CAPS),
            chapters=[
                TocChapter(
                    index=i,
                    title=e.title,
                    start_page=e.start,
                    end_page=e.end,
                    pages=e.pages,
                    chars=_chars_between(pages, e.start, e.end, skip),
                )
                for i, e in enumerate(res.entries, 1)
            ],
            advice=advice,
            ai_written=by_ai,
            gated=gated,
        )
        body = json.dumps(report.model_dump(by_alias=True, mode="json"), ensure_ascii=False).encode()
        self.storage.put(toc_key(ref.class_id, ref.id), body, "application/json")
        self.progress.emit(job_id, EVENT_TOC_READY, {"documentId": str(ref.id), "level": est.level, "gated": gated})
        if gated:
            self.progress.report(job_id, 100, STEP_AWAITING)
            log.info("job %s: giáo trình ~%d nút (%s) – dừng chờ GV chọn chương", job_id, est.nodes, est.level)
        return gated


@celery.task(name="app.workers.documents.process_syllabus")
def process_syllabus(document_id: str, job_id: str) -> None:
    """Đẩy bởi SyllabusService.upload (C2-08), task_id = job_id. Không tự thử lại: lỗi ⇒ FAILED, GV tải lại.
    Bóc chữ xong (PARSED) → dò mục lục + ước cỡ (`TocStep`); cỡ nhỏ (hoặc cổng tắt) thì nối `build_tree` để thanh
    tiến độ chạy tiếp tới cây nháp (C1-10), cỡ lớn thì dừng chờ GV chọn chương."""
    from app.ai.gateway import get_gateway

    gated = False
    with open_preprocessor() as pre:
        pages = pre.run(UUID(document_id), job_id)
        ref = pre.repo.get(UUID(document_id)) if pages else None
        if ref is not None:
            gated = TocStep(pre.storage, pre.progress, get_gateway()).run(ref, job_id, pages)
    if pages and not gated:
        build_tree.apply_async(args=[document_id, job_id], queue="documents")


# --- C1-10: dựng cây nháp ---------------------------------------------------------------------------

EVENT_TREE_GENERATED = "tree.generated"
RUBRIC_WORKERS = 8
MSG_NO_PAGES = "Không đọc lại được văn bản đã bóc của tài liệu – hãy tải lại"
MSG_TREE_AI = "AI tạm thời không dựng được cây – hãy thử lại sau ít phút"


class TreeDrafter:
    """Đọc `pages.json` (C1-09) → `TreeBuilder` → `SkillTreeService.create_version(sanitize_graph=True)` (phá chu
    trình / rút gọn bắc cầu, mục 6.1.4) → nhúng giáo trình + sinh rubric nháp cho mọi nút (C1-11)
    → phát `tree.generated {versionId}`. Lỗi ⇒ tiến độ FAILED + lưu lỗi trên tài liệu."""

    def __init__(self, db: Any, storage: ObjectStorage, progress: JobProgressSink, builder: Any) -> None:
        self.db, self.storage, self.progress, self.builder = db, storage, progress, builder

    def _scope(self, doc: Any, pages: list[dict[str, Any]], ranges: list[list[int]] | None) -> list[dict[str, Any]]:
        """Bỏ trang mục lục (đã biết từ `toc.json`) và, nếu GV chọn khoảng trang, chỉ giữ các khoảng đó.
        Số trang giữ nguyên để trích dẫn trang vẫn đúng."""
        skip: set[int] = set()
        try:
            toc = json.loads(self.storage.get(sibling_url(doc.file_url, doc.class_id, toc_key(doc.class_id, doc.id))))
            skip = set(toc.get("tocPages", []))
        except (StorageUnavailable, KeyError, ValueError):
            pass  # không có báo cáo mục lục (tài liệu cũ) ⇒ giữ nguyên
        keep = {n for a, b in ranges or [] for n in range(a, b + 1)}
        return [p for p in pages if p["number"] not in skip and (not keep or p["number"] in keep)]

    def run(
        self,
        document_id: UUID,
        job_id: str,
        ranges: list[list[int]] | None = None,
        detail: str | None = None,
        lazy_rubric: bool = False,
    ) -> UUID | None:
        """`detail`: mức chi tiết GV chọn (SUMMARY/STANDARD/DETAILED) ⇒ trần khái niệm mỗi đoạn; None ⇒ mặc định.
        `lazy_rubric`: chưa sinh rubric (GV cắt tỉa cây rồi sinh một lượt bằng `fill_rubrics`)."""
        from app.api.deps import CurrentUser
        from app.services.syllabus_toc import DETAIL_CAPS

        if detail in DETAIL_CAPS:
            self.builder.max_concepts = DETAIL_CAPS[detail]
        from app.core.errors import AppError
        from app.models.enums import Role
        from app.models.users import SyllabusDocument
        from app.services.skill_tree import SkillTreeService

        prog = _Progress(self.progress, job_id)
        doc = self.db.get(SyllabusDocument, document_id)
        if doc is None:
            log.error("job %s: không có tài liệu %s", job_id, document_id)
            prog.fail()
            return None
        try:
            try:
                raw = self.storage.get(self.storage_url(doc))
                pages = json.loads(raw)["pages"]
            except (StorageUnavailable, KeyError, ValueError):
                raise AppError(500, "PAGES_UNAVAILABLE", MSG_NO_PAGES) from None
            pages = self._scope(doc, pages, ranges)
            prog(10, "CONCEPTS")
            from app.ai import demo

            demo_tree = False
            try:
                body = self.builder.build(pages, prog)
            except AppError as exc:
                if not demo.active(exc):
                    raise
                log.warning("job %s: LLM mất kết nối, dùng cây mẫu (DEMO_MODE)", job_id)
                body, demo_tree = demo.seed_tree(), True  # C1-13: cây + rubric lưu sẵn
            user = CurrentUser(id=doc.uploaded_by, role=Role.LECTURER)
            removed: list[tuple[str, str]] = []
            trees = SkillTreeService(self.db)
            version = trees.create_version(doc.class_id, user, body, sanitize_graph=True, removed_edges=removed)
            doc.error_message = None  # dựng lại thành công: bỏ thông báo hủy / lỗi của lần trước
            self.db.commit()
            prog(92, "INDEXING")
            try:
                RetrievalService(self.db).index_document(doc.id, pages)  # C1-11: nhúng đoạn giáo trình vào pgvector
            except AppError as exc:
                # Cây đã commit: không nhúng được giáo trình thì rubric không truy hồi được, nhưng cây vẫn dùng được.
                self.db.rollback()
                log.warning("job %s: không nhúng được giáo trình, bỏ qua: %s", job_id, exc.message)
            if not lazy_rubric:
                prog(95, "RUBRICS")
                missing = self._rubrics(trees, doc.class_id, version, user, only_missing=demo_tree)
                if missing:
                    doc.error_message = f"{missing} nút chưa sinh được rubric – hãy bấm sinh lại ở từng nút"
                    self.db.commit()
            prog(100, "DONE")
            self.progress.emit(job_id, EVENT_TREE_GENERATED, {"versionId": str(version.id)})
            log.info(
                "job %s: cây nháp %s – %d nút, %d cạnh (bỏ %d cạnh khi hậu xử lý)",
                job_id, version.id, len(version.nodes), len(version.edges), len(removed),
            )  # fmt: skip
            return version.id
        except JobCancelled:
            log.info("job %s: người dùng đã hủy dựng cây từ %s", job_id, document_id)
            self._cancel(doc, prog)
            return None
        except AppError as exc:
            self._fail(doc, prog, exc.message if exc.status < 500 or exc.code == "PAGES_UNAVAILABLE" else MSG_TREE_AI)
        except Exception:
            log.exception("job %s: lỗi không mong đợi khi dựng cây từ %s", job_id, document_id)
            self._fail(doc, prog, MSG_UNEXPECTED)
            raise
        return None

    def fill_rubrics(self, class_id: UUID, user_id: UUID) -> int:
        """Sinh rubric (chưa duyệt) cho các nút CHƯA có rubric của bản nháp hiện tại – dùng sau khi GV cắt tỉa cây dựng
        với `lazy_rubric`. Bản đã phát hành thì không làm gì. Trả số nút lỗi (GV bấm sinh lại ở từng nút)."""
        from app.api.deps import CurrentUser
        from app.models.enums import Role
        from app.services.skill_tree import SkillTreeService

        user = CurrentUser(id=user_id, role=Role.LECTURER)
        trees = SkillTreeService(self.db)
        version = trees.get_class_tree(class_id, user=user, draft=True)
        if version.status not in ("DRAFT", "EDITING"):
            return 0
        return self._rubrics(trees, class_id, version, user, only_missing=True)

    def _rubrics(self, trees: Any, class_id: UUID, version: Any, user: Any, only_missing: bool = False) -> int:
        """Sinh rubric (chưa duyệt) cho mọi nút: truy hồi tuần tự trên phiên CSDL, LLM chạy song song, ghi tuần tự.
        Trả số nút bị lỗi (nút đó để trống, GV bấm sinh lại)."""
        from app.ai import demo
        from app.ai.agents.rubric_generator import TOP_PASSAGES, RubricGenerator, class_params, query_for
        from app.core.errors import AppError
        from app.models.users import ClassSection

        gw = self.builder.gw
        retrieval = RetrievalService(self.db, gw)
        gen = RubricGenerator(gw, **class_params(self.db.get(ClassSection, class_id)))
        todo = [n for n in version.nodes if not (only_missing and n.rubric)]  # cây mẫu đã có rubric lưu sẵn
        jobs, failed = [], 0
        for n in todo:
            try:
                jobs.append((n, retrieval.retrieve(class_id, query_for(n), TOP_PASSAGES)))
            except AppError as exc:
                # Cây đã lưu: lỗi truy hồi/nhúng của một nút (kể cả không ở DEMO_MODE) chỉ làm nút đó để trống, GV sinh
                # lại sau; không làm hỏng cả job.
                if not demo.active(exc):
                    log.warning("không truy hồi được đoạn giáo trình cho nút %s: %s", n.key, exc.message)
                self.db.rollback()
                failed += 1
        with ThreadPoolExecutor(RUBRIC_WORKERS) as ex:
            futures = [(n, ex.submit(gen.generate, n, passages)) for n, passages in jobs]
            for n, fut in futures:
                try:
                    trees.put_rubric(n.id, fut.result(), user, only_if_missing=True)  # không đè rubric GV vừa nhập
                except Exception:
                    log.exception("không sinh được rubric cho nút %s", n.key)
                    self.db.rollback()
                    failed += 1
        return failed

    @staticmethod
    def storage_url(doc: Any) -> str:
        # file_url dạng s3://bucket/syllabi/{classId}/{docId}.pdf ⇒ cùng bucket, khóa pages_key
        head = doc.file_url.rsplit(f"/syllabi/{doc.class_id}/", 1)[0]
        return f"{head}/{pages_key(doc.class_id, doc.id)}"

    def _fail(self, doc: Any, prog: _Progress, message: str) -> None:
        try:
            self.db.rollback()
            doc = self.db.get(type(doc), doc.id)
            doc.error_message = message  # trạng thái PARSED giữ nguyên: văn bản đã bóc vẫn dùng được khi thử lại
            self.db.commit()
        finally:
            prog.fail()

    def _cancel(self, doc: Any, prog: _Progress, message: str = "Đã hủy theo yêu cầu") -> None:
        try:
            self.db.rollback()
            doc = self.db.get(type(doc), doc.id)
            if doc is not None:
                doc.error_message = message
                self.db.commit()
        finally:
            prog.cancel()


@contextmanager
def open_tree_drafter() -> Iterator[TreeDrafter]:
    from app.ai.agents.tree_builder import TreeBuilder
    from app.ai.gateway import get_gateway
    from app.db.session import SessionLocal
    from app.services.storage import default_storage

    db = SessionLocal()
    try:
        yield TreeDrafter(db, default_storage(), RedisJobProgress(), TreeBuilder(get_gateway()))
    finally:
        db.close()


@celery.task(name="app.workers.documents.build_tree")
def build_tree(
    document_id: str,
    job_id: str,
    ranges: list[list[int]] | None = None,
    detail: str | None = None,
    lazy_rubric: bool = False,
) -> None:
    """Trích khái niệm (JSON Schema mục 6.1.2) → tiên quyết (6.1.3) → DAG (C2-09). Rubric (6.1.5): C1-11.
    `ranges`: các khoảng trang [từ, đến] GV đã chọn sau cảnh báo cỡ giáo trình; None ⇒ toàn bộ (trừ trang mục lục).
    `detail`, `lazy_rubric`: mức chi tiết và việc hoãn sinh rubric, cũng do GV chọn ở bước đó."""
    with open_tree_drafter() as drafter:
        drafter.run(UUID(document_id), job_id, ranges, detail, lazy_rubric)


@celery.task(name="app.workers.documents.fill_rubrics")
def fill_rubrics(class_id: str, user_id: str) -> None:
    """Sinh rubric cho các nút còn thiếu của bản nháp (GV bấm ở trình sửa cây). Giao diện hỏi lại cây định kỳ."""
    try:
        with open_tree_drafter() as drafter:
            failed = drafter.fill_rubrics(UUID(class_id), UUID(user_id))
    finally:
        RedisJobProgress().unlock_fill(class_id)  # nhả khóa kể cả khi lỗi để GV bấm lại được
    if failed:
        log.warning("lớp %s: %d nút chưa sinh được rubric", class_id, failed)
