"""Bước mục lục trước khi dựng cây (TocStep) và lọc trang khi dựng (TreeDrafter._scope) – không cần DB."""

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.storage import InMemoryStorage
from app.services.syllabus import DocumentRef, toc_key
from app.workers.documents import InMemoryJobProgress, Page, TocStep, TreeDrafter, _chars_between

TOC_PAGE = (
    "MỤC LỤC\nChương 1. Giới thiệu ........ 3\nChương 2. Mảng ........ 10\n"
    "Chương 3. Con trỏ ........ 18\nChương 4. Hàm ........ 25"
)


class Gw:
    def __init__(self):
        self.calls = 0

    def call_json(self, schema, messages, **kw):
        self.calls += 1
        draft = {"message": "Nên chọn chương trọng tâm.", "keep": [1, 2], "skip": [{"index": 4, "reason": "ôn tập"}]}
        return schema.model_validate(draft)


def _pages(n: int, chars_per_page: int = 3000) -> list[Page]:  # 30 trang ≈ 10 đoạn ≈ 110 nút ⇒ mức WARN
    body = "từ khóa dài " * (chars_per_page // 9)
    pages = [Page(number=i, text=f"Nội dung {i} {body}") for i in range(1, n + 1)]
    pages[1].text = TOC_PAGE
    return pages


@pytest.fixture
def world(monkeypatch):
    cfg = SimpleNamespace(toc_gate_enabled=True, toc_warn_nodes=60, toc_max_nodes=150)
    monkeypatch.setattr("app.core.config.get_settings", lambda: cfg)
    storage, progress, gw = InMemoryStorage("whybi"), InMemoryJobProgress(), Gw()
    doc_id, class_id = uuid4(), uuid4()
    url = storage.put(f"syllabi/{class_id}/{doc_id}.docx", b"x", "x")
    ref = DocumentRef(doc_id, class_id, url, "docx")
    return SimpleNamespace(
        cfg=cfg, storage=storage, progress=progress, gw=gw, ref=ref, step=TocStep(storage, progress, gw)
    )


def _toc(w) -> dict:
    return json.loads(w.storage.objects[toc_key(w.ref.class_id, w.ref.id)])


def test_giao_trinh_lon_dung_cho_gv_chon_chuong(world):
    w = world
    assert w.step.run(w.ref, "job1", _pages(30)) is True
    toc = _toc(w)
    assert toc["gated"] and toc["level"] == "WARN" and toc["aiWritten"] and toc["tocPages"] == [2]
    assert [c["title"] for c in toc["chapters"]][:2] == ["Chương 1. Giới thiệu", "Chương 2. Mảng"]
    assert toc["advice"]["keep"] == [1, 2] and toc["advice"]["skip"][0]["index"] == 4
    assert w.gw.calls == 1
    assert toc["nodesPerChunk"] == {"SUMMARY": 4, "STANDARD": 8, "DETAILED": 11} and toc["charsPerChunk"] == 7000
    assert toc["detailCaps"]["SUMMARY"] == 4
    assert toc["offset"] is None and all(c["chars"] == 0 for c in toc["chapters"])  # chưa biết trang ⇒ chưa đếm được
    events = [(e[1], e[2]) for e in w.progress.events]
    assert ("syllabus.toc_ready", {"documentId": str(w.ref.id), "level": "WARN", "gated": True}) in events
    assert any(e[1] == "job.progress" and e[2]["step"] == "AWAITING_SELECTION" for e in w.progress.events)


def test_dem_ky_tu_chuong_bo_trang_muc_luc_va_trang_chua_biet():
    pages = [Page(number=i, text="ab cd") for i in range(1, 6)]  # mỗi trang 4 ký tự không tính khoảng trắng
    assert _chars_between(pages, 2, 4, {3}) == 8
    assert _chars_between(pages, None, 4, set()) == 0


def test_cong_tat_van_canh_bao_nhung_khong_dung(world):
    w = world
    w.cfg.toc_gate_enabled = False
    assert w.step.run(w.ref, "job1", _pages(30)) is False
    assert _toc(w)["gated"] is False and _toc(w)["level"] == "WARN"


def test_giao_trinh_nho_khong_ton_luot_ai(world):
    w = world
    assert w.step.run(w.ref, "job1", _pages(5, chars_per_page=900)) is False
    assert _toc(w)["level"] == "OK" and w.gw.calls == 0
    assert any(e[1] == "syllabus.toc_ready" for e in w.progress.events)


def test_loi_bat_ky_thi_khong_chan_luong_dung_cay(world):
    w = world

    def boom(*a, **k):
        raise RuntimeError("kho lưu trữ hỏng")

    w.storage.put = boom
    assert w.step.run(w.ref, "job1", _pages(30)) is False


def test_dung_cay_bo_trang_muc_luc_va_chi_giu_khoang_gv_chon(world):
    w = world
    w.step.run(w.ref, "job1", _pages(30))
    drafter = TreeDrafter(None, w.storage, w.progress, None)
    doc = SimpleNamespace(file_url=w.ref.file_url, class_id=w.ref.class_id, id=w.ref.id)
    pages = [{"number": i, "text": "x"} for i in range(1, 31)]
    assert [p["number"] for p in drafter._scope(doc, pages, None)] == [i for i in range(1, 31) if i != 2]
    assert [p["number"] for p in drafter._scope(doc, pages, [[1, 4], [20, 21]])] == [1, 3, 4, 20, 21]


def test_tai_lieu_cu_khong_co_bao_cao_muc_luc_thi_giu_nguyen(world):
    w = world
    drafter = TreeDrafter(None, w.storage, w.progress, None)
    doc = SimpleNamespace(file_url=w.ref.file_url, class_id=w.ref.class_id, id=w.ref.id)
    pages = [{"number": i, "text": "x"} for i in range(1, 6)]
    assert drafter._scope(doc, pages, None) == pages


def test_muc_luc_mo_ho_goi_ai_phan_loai_chuong(world, monkeypatch):
    w = world
    called_schemas = []

    def mock_call_json(schema, messages, **kw):
        called_schemas.append(schema.__name__)
        if schema.__name__ == "TocLabels":
            return schema.model_validate(
                {
                    "labels": [
                        {"index": 1, "kind": "FRONT"},
                        {"index": 2, "kind": "CHAPTER"},
                        {"index": 3, "kind": "CHAPTER"},
                        {"index": 4, "kind": "BACK"},
                    ]
                }
            )
        return schema.model_validate(
            {
                "message": "Nên tập trung 2 chương chính.",
                "keep": [1, 2],
                "skip": [],
            }
        )

    monkeypatch.setattr(w.gw, "call_json", mock_call_json)

    ambiguous_toc = (
        "MỤC LỤC\nLời nói đầu ........ 3\nCấu trúc dữ liệu ........ 10\n"
        "Giải thuật nâng cao ........ 18\nTài liệu tham khảo ........ 25"
    )
    pages = _pages(30)
    pages[1].text = ambiguous_toc

    assert w.step.run(w.ref, "job1", pages) is True
    toc = _toc(w)

    assert "TocLabels" in called_schemas
    assert "TocAdviceDraft" in called_schemas
    assert len(toc["chapters"]) == 2
    assert [c["title"] for c in toc["chapters"]] == ["Cấu trúc dữ liệu", "Giải thuật nâng cao"]
    assert toc["chapters"][0]["index"] == 1
    assert toc["chapters"][1]["index"] == 2


def test_huy_tien_trinh_khong_chay_tiep_toc_step(world):
    w = world
    w.progress.cancel("job1")
    assert w.progress.is_cancelled("job1") is True
    # Khi đã hủy, TocStep không chạy và trả về False
    assert w.step.run(w.ref, "job1", _pages(30)) is False


def test_progress_bao_loi_job_cancelled_khi_bi_huy(world):
    from app.workers.documents import JobCancelled, _Progress

    w = world
    w.progress.cancel("job_huy")
    prog = _Progress(w.progress, "job_huy")
    with pytest.raises(JobCancelled):
        prog(15, "CONCEPTS")
