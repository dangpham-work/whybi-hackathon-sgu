"""Cảnh báo cỡ giáo trình từ mục lục đã trích – gateway giả, không gọi mạng."""

from app.ai.agents.toc_advisor import TocAdviceDraft, TocLabels, advise, classify_chapters
from app.core.errors import AppError
from app.services.syllabus_toc import TocEntry, TocResult, estimate_size


def _res(n_chapters: int = 4, source: str = "toc_pages") -> TocResult:
    entries = [
        TocEntry(f"Chương {i}. Bài {i}", i * 10, start=i * 10 + 2, end=i * 10 + 11) for i in range(1, n_chapters + 1)
    ]
    return TocResult(source, entries, [2], 2, total_pages=120, total_chars=300_000)


class Gw:
    def __init__(self, draft=None, error=None):
        self.draft, self.error, self.calls = draft, error, []

    def call_json(self, schema, messages, **kw):
        self.calls.append(messages)
        if self.error:
            raise self.error
        return schema.model_validate(self.draft)


EST = estimate_size(300_000, 4, warn_nodes=60, max_nodes=150)


def test_ai_nhan_danh_sach_muc_luc_kem_ghi_chu_tu_trich_va_so_trang():
    gw = Gw({"message": "Nên khoanh vùng.", "keep": [1, 2], "skip": [{"index": 4, "reason": "bài tập"}]})
    advice, by_ai = advise(gw, _res(), EST, 60)
    system, user = gw.calls[0][0]["content"], gw.calls[0][1]["content"]
    assert by_ai and advice.keep == [1, 2] and advice.skip[0].index == 4
    assert "TỰ TRÍCH" in system and "trang mục lục in trong sách" in system and str(EST.nodes) in system
    assert "<toc_data>" in user and "1. Chương 1. Bài 1 – trang 12–21 (10 trang)" in user


def test_bo_chi_so_ngoai_danh_sach_trung_lap_va_chuong_vua_giu_vua_bo():
    draft = {
        "message": "x" * 2000,
        "keep": [1, 3, 99, 0],
        "skip": [{"index": 3, "reason": "r"}, {"index": 3, "reason": "r"}, {"index": 50, "reason": "r"}],
    }
    advice, _ = advise(Gw(draft), _res(), EST, 60)
    assert advice.keep == [1] and [s.index for s in advice.skip] == [3]  # 3 theo skip; 99, 0, 50 bị bỏ
    assert len(advice.message) == 800


def test_ai_loi_thi_dung_cau_mau_khong_nem_loi():
    advice, by_ai = advise(Gw(error=AppError(503, "LLM_UNAVAILABLE", "x")), _res(), EST, 60)
    assert not by_ai and "4 chương" in advice.message and "lượt gọi AI" in advice.message


def test_khong_co_muc_luc_thi_khong_goi_ai():
    gw = Gw({"message": "không được gọi"})
    res = TocResult("none", [], [], None, total_pages=120, total_chars=300_000)
    advice, by_ai = advise(gw, res, EST, 60)
    assert gw.calls == [] and not by_ai and "Không tìm thấy mục lục" in advice.message


def test_ban_nhap_hop_le_voi_gateway_fake():
    assert TocAdviceDraft.model_validate({"message": "mẫu"}).keep == []


def _mo_ho() -> TocResult:
    titles = ["Giáo trình CTDL", "Tổng quan", "Mảng", "Con trỏ", "Phụ lục"]
    entries = [TocEntry(t, i * 10, start=i * 10, end=i * 10 + 9) for i, t in enumerate(titles, 1)]
    return TocResult("bookmark", entries, [], 0, total_pages=100, total_chars=1, ambiguous=True)


def test_ai_phan_loai_bo_ten_sach_tong_quan_va_phu_luc_giu_nguyen_trang_cuoi():
    labels = {"labels": [{"index": 1, "kind": "FRONT"}, {"index": 2, "kind": "FRONT"}, {"index": 5, "kind": "BACK"}]}
    gw, res = Gw(labels), _mo_ho()
    assert classify_chapters(gw, res)
    assert [(e.title, e.start, e.end) for e in res.entries] == [("Mảng", 30, 39), ("Con trỏ", 40, 49)]
    assert not res.ambiguous
    assert "FRONT" in gw.calls[0][0]["content"] and "1. Giáo trình CTDL" in gw.calls[0][1]["content"]


def test_phan_loai_loi_hoac_con_duoi_2_chuong_thi_giu_nguyen():
    res = _mo_ho()
    assert not classify_chapters(Gw(error=AppError(503, "LLM_UNAVAILABLE", "x")), res) and len(res.entries) == 5
    tat_ca_bo = {"labels": [{"index": i, "kind": "FRONT"} for i in range(1, 6)]}
    assert not classify_chapters(Gw(tat_ca_bo), res) and len(res.entries) == 5 and res.ambiguous


def test_nhan_rong_cua_gateway_fake_khong_lam_mat_muc_nao():
    res = _mo_ho()
    assert classify_chapters(Gw(TocLabels().model_dump()), res) and len(res.entries) == 5
