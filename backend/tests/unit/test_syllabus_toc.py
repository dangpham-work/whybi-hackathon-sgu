"""Dò mục lục chương của giáo trình (services/syllabus_toc.py) – dữ liệu tổng hợp, không cần tệp thật."""

import math

from app.services.syllabus_toc import estimate_size, find_toc, parse_toc_lines, scan_window

CHAPTERS = [
    ("Chương 1. Giới thiệu", 1),
    ("Chương 2. Mảng và con trỏ", 9),
    ("Chương 3. Danh sách liên kết", 17),
    ("Chương 4. Ngăn xếp và hàng đợi", 25),
]


def _toc_text() -> str:
    # có cả dòng "Phần" (cấp trên) và mục con "n.n" để kiểm việc chỉ lấy cấp chương
    rows: list[tuple[str, int | None]] = [("MỤC LỤC", None), ("Phần 1. Nền tảng", 1)]
    for i, (title, page) in enumerate(CHAPTERS, 1):
        rows.append((title, page))
        rows.append((f"{i}.1 Khái niệm chính", page + 1))
    return "\n".join(t if p is None else f"{t} {'.' * 12} {p}" for t, p in rows)


def _doc(n: int, toc_at: list[int], offset: int, toc_text: str) -> list[dict]:
    """n trang; mục lục ở các trang `toc_at`; chương k mở ở trang in `CHAPTERS[k][1]` ⇒ trang tệp = in + offset."""
    starts = {page + offset: title for title, page in CHAPTERS}
    rows = toc_text.splitlines()
    size = math.ceil(len(rows) / len(toc_at))  # mục lục dài ⇒ chia đều, trang sau nối tiếp số trang của trang trước
    pages = []
    for i in range(1, n + 1):
        if i in toc_at:
            k = toc_at.index(i)
            text = "\n".join(rows[k * size : (k + 1) * size])
        elif i in starts:
            text = starts[i].upper().replace(". ", "\n", 1) + "\nNội dung bài giảng."
        else:
            text = f"Nội dung trang {i}.\nXem Chương 2. Mảng và con trỏ để biết thêm."  # tham chiếu giữa dòng
        pages.append({"number": i, "text": text, "headings": []})
    return pages


def test_scan_window_ti_le_va_chan():
    assert scan_window(30) == 5  # 5 % chỉ ~2 trang ⇒ nâng lên tối thiểu
    assert scan_window(200) == 10
    assert scan_window(2000) == 20  # chặn trên


def test_uoc_luong_co_theo_ky_tu_khong_theo_trang():
    nho = estimate_size(total_chars=30_000, n_chapters=2, warn_nodes=60, max_nodes=150)
    assert (nho.chunks, nho.nodes, nho.level) == (5, 55, "OK")  # 30 000 ký tự ⇒ 5 đoạn dù chỉ 2 chương
    lon = estimate_size(total_chars=70_000, n_chapters=0, warn_nodes=60, max_nodes=150)
    assert lon.level == "WARN" and lon.llm_calls > lon.nodes
    qua = estimate_size(total_chars=400_000, n_chapters=30, warn_nodes=60, max_nodes=150)
    assert qua.level == "TOO_LARGE"
    assert estimate_size(0, 0, 60, 150).level == "OK"


def test_muc_chi_tiet_va_rubric_sau_giam_so_nut_va_luot_goi():
    full = estimate_size(56_000, 0, 60, 150)  # 8 đoạn, chi tiết (≤12 nút/đoạn): 88 nút, 8 + 88 + 88 lượt
    assert (full.chunks, full.nodes, full.llm_calls, full.level) == (8, 88, 184, "WARN")
    tom_luoc = estimate_size(56_000, 0, 60, 150, detail="SUMMARY")
    chuan = estimate_size(56_000, 0, 60, 150, detail="STANDARD")
    assert tom_luoc.nodes < chuan.nodes < full.nodes and tom_luoc.level == "OK"
    lazy = estimate_size(56_000, 0, 60, 150, lazy_rubric=True)
    assert lazy.nodes == full.nodes and lazy.llm_calls == 8 + 88  # bỏ N lượt rubric


def test_dong_chi_co_chuong_khong_so_trang_bi_loai():
    assert parse_toc_lines("Chương 1\nChương 2\nChương 3\nChương 4") == []
    assert parse_toc_lines("Chương 1. Giới thiệu ...... 5") == [("Chương 1. Giới thiệu", 5)]
    assert parse_toc_lines("bộ nhớ đệm, 88") == []  # chỉ mục: tiêu đề kết thúc bằng dấu phẩy


def test_muc_luc_o_dau_sach():
    r = find_toc(_doc(40, toc_at=[2], offset=2, toc_text=_toc_text()))
    assert r.source == "toc_pages" and r.toc_pages == [2] and r.offset == 2
    assert [e.title for e in r.entries] == [t for t, _ in CHAPTERS]  # bỏ "Phần" và mục con n.n
    assert [(e.start, e.end) for e in r.entries] == [(3, 10), (11, 18), (19, 26), (27, 40)]
    assert r.total_pages == 40 and r.total_chars > 0


def test_muc_luc_o_cuoi_sach_chuong_cuoi_ket_thuc_truoc_muc_luc():
    r = find_toc(_doc(40, toc_at=[39, 40], offset=1, toc_text=_toc_text()))
    assert r.source == "toc_pages" and r.toc_pages == [39, 40]
    assert [e.start for e in r.entries] == [2, 10, 18, 26]
    assert r.entries[-1].end == 38


def test_chi_muc_cuoi_sach_khong_nham_la_muc_luc():
    index = "\n".join(["bộ nhớ đệm 88", "con trỏ hàm 12", "ngăn xếp động 40", "hàng đợi vòng 7", "danh sách đôi 31"])
    r = find_toc(_doc(40, toc_at=[39], offset=0, toc_text=index))  # 5 dòng đủ ngưỡng ⇒ chỉ số trang lộn xộn loại nó
    assert r.source == "none" and r.entries == []


def test_co_muc_luc_nhung_khong_thay_chuong_trong_than_bai_thi_khong_doan_do_lech():
    pages = [{"number": i, "text": f"Nội dung {i}", "headings": []} for i in range(1, 41)]
    pages[1]["text"] = _toc_text()
    r = find_toc(pages)
    assert r.source == "toc_pages" and r.offset is None
    assert all(e.start is None for e in r.entries)


def test_bookmark_uu_tien_va_lay_cap_chuong():
    pages = [{"number": i, "text": "x", "headings": []} for i in range(1, 41)]
    marks = [(1, "Chương 1", 3), (2, "1.1 Khái niệm", 4), (1, "Chương 2", 11), (1, "Chương 3", 19), (1, "Hỏng", -1)]
    r = find_toc(pages, marks)
    assert r.source == "bookmark" and r.offset == 0
    assert [(e.title, e.start, e.end) for e in r.entries] == [
        ("Chương 1", 3, 10),
        ("Chương 2", 11, 18),
        ("Chương 3", 19, 40),
    ]


def test_bookmark_bo_ten_giao_trinh_va_phan_tong_quan_chi_giu_chuong():
    """Ca thật: bookmark cấp 1 gồm tên trường/năm, 'PHẦN TỔNG QUAN' rồi các chương."""
    pages = [{"number": i, "text": "x", "headings": []} for i in range(1, 110)]
    marks = [
        (1, "ĐẠI HỌC CẦN THƠ - 12/2003", 1),
        (1, "PHẦN TỔNG QUAN", 4),
        (1, "Chương 1: KĨ THUẬT PHÂN TÍCH", 6),
        (1, "Chương 2: SẮP XẾP", 23),
        (1, "Chương 3: THIẾT KẾ", 50),
        (1, "Chương 4: LƯU TRỮ NGOÀI", 90),
    ]
    r = find_toc(pages, marks)
    assert [e.title for e in r.entries] == [m[1] for m in marks[2:]] and not r.ambiguous
    assert [(e.start, e.end) for e in r.entries] == [(6, 22), (23, 49), (50, 89), (90, 109)]


def test_bookmark_khong_co_tu_khoa_chuong_thi_danh_dau_mo_ho_de_nho_ai_phan_loai():
    pages = [{"number": i, "text": "x", "headings": []} for i in range(1, 60)]
    marks = [(1, "Giáo trình CTDL", 1), (1, "Mảng", 5), (1, "Con trỏ", 20), (1, "Phụ lục", 50)]
    r = find_toc(pages, marks)
    assert r.ambiguous and len(r.entries) == 4 and r.entries[1].end == 19


def test_khong_co_muc_luc():
    pages = [{"number": i, "text": f"Nội dung trang {i}", "headings": []} for i in range(1, 41)]
    r = find_toc(pages)
    assert r.source == "none" and r.entries == [] and r.total_pages == 40
