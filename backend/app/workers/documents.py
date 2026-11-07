"""Hàng đợi `documents` – tiền xử lý giáo trình và sinh cây (UC06, Hình 4.16). Chủ: Đăng (C1-09…C1-11).

PyMuPDF (PDF) · python-docx (DOCX) · Tesseract `vie` cho bản quét · chia đoạn ~500 token, chồng 50 ·
embedding → document_chunks · báo tiến độ kênh job:{jobId}.
"""

from app.workers.celery_app import celery


@celery.task(name="app.workers.documents.process_syllabus")
def process_syllabus(document_id: str, job_id: str) -> None:
    raise NotImplementedError("C1-09")


@celery.task(name="app.workers.documents.build_tree")
def build_tree(document_id: str, job_id: str) -> None:
    """Trích khái niệm (JSON Schema mục 6.1.2) → tiên quyết (6.1.3) → DAG (C2-09) → rubric (6.1.5)."""
    raise NotImplementedError("C1-10")
