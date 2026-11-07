"""C2-08 – Xong khi: tệp sai định dạng hoặc quá 20 MB bị từ chối có thông báo (phần hàm thuần, không cần CSDL).

TC01 (Bảng 7.x): tệp .exe đổi đuôi .pdf ⇒ 422 INVALID_FILE.
"""

import io
import os
import zipfile
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.classes import JoinRequest
from app.core.errors import AppError
from app.services.classes import JOIN_CODE_ALPHABET, new_join_code
from app.services.storage import InMemoryStorage, MinioStorage
from app.services.syllabus import MAX_BYTES, validate_syllabus

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
EXE = b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 64


def docx_bytes(*, with_document: bool = True) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        if with_document:
            z.writestr("word/document.xml", "<w:document/>")
        else:
            z.writestr("hello.txt", "không phải docx")
    return buf.getvalue()


def rejected(filename: str | None, data: bytes) -> AppError:
    with pytest.raises(AppError) as exc:
        validate_syllabus(filename, data)
    return exc.value


def test_pdf_and_docx_accepted():
    assert validate_syllabus("giao-trinh.pdf", PDF) == "pdf"
    assert validate_syllabus("Giao Trinh.DOCX", docx_bytes()) == "docx"


def test_exe_renamed_pdf_rejected_tc01():
    err = rejected("giao-trinh.pdf", EXE)
    assert (err.status, err.code) == (422, "INVALID_FILE")
    assert err.details["reason"] == "CONTENT_MISMATCH"
    assert "PDF" in err.message


@pytest.mark.parametrize("name", ["virus.exe", "ghi-chu.txt", "slide.pptx", "giao-trinh", None, "bang.doc"])
def test_other_extensions_rejected(name):
    err = rejected(name, PDF)
    assert (err.status, err.code) == (422, "INVALID_FILE")
    assert err.details["reason"] == "EXTENSION" and err.details["allowed"] == ["pdf", "docx"]


def test_zip_renamed_docx_rejected():
    err = rejected("giao-trinh.docx", docx_bytes(with_document=False))
    assert err.code == "INVALID_FILE" and err.details["reason"] == "CONTENT_MISMATCH"
    assert rejected("giao-trinh.docx", PDF).code == "INVALID_FILE"


def test_empty_file_rejected():
    err = rejected("giao-trinh.pdf", b"")
    assert err.code == "INVALID_FILE" and err.details["reason"] == "EMPTY"


def test_over_20_mb_rejected_with_message():
    assert MAX_BYTES == 20 * 1024 * 1024
    err = rejected("giao-trinh.pdf", PDF + b"\0" * (MAX_BYTES + 1 - len(PDF)))
    assert (err.status, err.code) == (422, "FILE_TOO_LARGE")
    assert "20 MB" in err.message and err.details["maxMb"] == 20


def test_exactly_20_mb_accepted():
    assert validate_syllabus("giao-trinh.pdf", PDF + b"\0" * (MAX_BYTES - len(PDF))) == "pdf"


# --- Mã tham gia ---------------------------------------------------------------------------------


def test_join_code_is_8_unambiguous_chars():
    codes = {new_join_code() for _ in range(200)}
    assert len(codes) > 190
    for c in codes:
        assert len(c) == 8 and set(c) <= set(JOIN_CODE_ALPHABET)
    assert not set("O0I1") & set(JOIN_CODE_ALPHABET)


def test_join_request_normalises_and_validates():
    assert JoinRequest(join_code=" ctdl2026 ").join_code == "CTDL2026"
    assert JoinRequest.model_validate({"joinCode": "W3X8NB1D"}).join_code == "W3X8NB1D"
    for bad in ["ABC", "ABCDEFGHI", "CTDL-026", "", "CTĐL2026"]:
        with pytest.raises(ValidationError):
            JoinRequest(join_code=bad)


# --- Kho đối tượng -------------------------------------------------------------------------------


def test_in_memory_storage_put_remove():
    s = InMemoryStorage("whybi")
    url = s.put("syllabi/a/b.pdf", PDF, "application/pdf")
    assert url == "s3://whybi/syllabi/a/b.pdf" and s.objects["syllabi/a/b.pdf"] == PDF
    s.remove(url)
    assert s.objects == {}


S3 = os.getenv("TEST_S3_ENDPOINT")


@pytest.mark.skipif(not S3, reason="đặt TEST_S3_ENDPOINT (vd. http://localhost:9000) để thử MinIO thật")
def test_minio_storage_creates_missing_bucket():
    bucket = f"c208-test-{uuid4().hex[:8]}"
    key, secret = os.getenv("TEST_S3_ACCESS_KEY", "whybi"), os.getenv("TEST_S3_SECRET_KEY", "whybi-minio-secret")
    s = MinioStorage(S3, key, secret, bucket)
    assert not s.client.bucket_exists(bucket)
    url = s.put("syllabi/x/y.pdf", PDF, "application/pdf")
    assert url == f"s3://{bucket}/syllabi/x/y.pdf"
    assert s.client.get_object(bucket, "syllabi/x/y.pdf").read() == PDF
    s.remove(url)
    s.client.remove_bucket(bucket)
