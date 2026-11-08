"""Dò mục lục chương của giáo trình để biết sách có những chương nào, mỗi chương từ trang nào tới trang nào.

KHÔNG tốn token (thuần Python), CHƯA nối vào luồng dựng cây – chạy tay để thử:
    uv run python -m app.services.syllabus_toc <giaotrinh.pdf>

Thứ tự thử (bước trước đủ thì dừng):
1. Bookmark (outline) có sẵn trong tệp – chính xác nhất, số trang là trang thật.
2. Trang mục lục in sẵn ở ~5 % đầu và cuối tài liệu: trang nào có ≥ 4 dòng "tiêu đề …… số trang" với số trang
   tăng dần thì là mục lục (chỉ mục / tài liệu tham khảo có số trang lộn xộn nên bị loại). Số trang in trong sách
   thường lệch với trang của tệp (bìa, lời nói đầu) ⇒ tính độ lệch bằng cách tìm tiêu đề chương trong thân bài.
3. Không có ⇒ `source="none"`, để bước sau (dò theo tiêu đề cỡ chữ lớn / gom theo trang) xử lý.

Đầu vào `pages` đúng dạng `pages.json` của C1-09: `[{number, text, headings}]`, number bắt đầu từ 1.
"""

import math
import re
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

WINDOW_PCT = 0.05  # dò ~5 % trang ở đầu và ở cuối
WINDOW_MIN, WINDOW_MAX = 5, 20  # tài liệu ngắn vẫn dò ≥ 5 trang; sách dày không quét quá 20 trang mỗi đầu
MIN_LINES_PER_PAGE = 4  # trang mục lục phải có ≥ 4 dòng đúng dạng (trang nối tiếp: ≥ 2)
MIN_ASCENDING = 0.8  # ≥ 80 % cặp dòng liền kề có số trang không giảm
MIN_CHAPTERS = 2
CALIBRATE_N = 6  # dùng tối đa 6 chương đầu để tính độ lệch số trang

# tiêu đề + (chấm dẫn hoặc khoảng trắng) + số trang ở cuối dòng
_LINE = re.compile(r"^(?P<title>.+?)(?P<sep>\s*[.·…_]{2,}\s*|\s+)(?P<page>\d{1,4})$")
_LEADER = re.compile(r"[.·…_]{2,}")
_HEAD = re.compile(r"^(chương|chapter|bài|phần|unit|lesson|part|module|tuần|buổi|topic)\s+(\d+|[ivxlc]+)\b", re.I)
_SUB = re.compile(r"^\d+\.\d+")  # mục con "1.1 …"
_TOP_NUM = re.compile(r"^\d+[.)]?\s+\D")  # "1. Giới thiệu" / "1 Introduction"


@dataclass
class TocEntry:
    title: str
    printed_page: int  # số trang ghi trong mục lục (bookmark: chính là trang của tệp)
    start: int | None = None  # trang đầu trong tệp (bắt đầu từ 1); None ⇒ chưa biết độ lệch
    end: int | None = None

    @property
    def pages(self) -> int | None:
        return None if self.start is None or self.end is None else self.end - self.start + 1


@dataclass
class TocResult:
    source: str  # "bookmark" | "toc_pages" | "none"
    entries: list[TocEntry] = field(default_factory=list)
    toc_pages: list[int] = field(default_factory=list)  # trang mục lục – nên loại khi gửi AI trích khái niệm
    offset: int | None = None  # trang tệp = trang in + offset
    total_pages: int = 0
    total_chars: int = 0  # ký tự không tính khoảng trắng – ước độ lớn tài liệu
    ambiguous: bool = False  # True ⇒ không nhận ra chương bằng từ khóa / số thứ tự, có thể lẫn tên sách, phụ lục…

    def summary(self) -> str:
        src = {"bookmark": "bookmark của tệp", "toc_pages": f"trang mục lục in sẵn {self.toc_pages}"}.get(
            self.source, "KHÔNG tìm thấy mục lục"
        )
        lines = [
            f"Nguồn: {src}",
            f"Tài liệu: {self.total_pages} trang, ~{self.total_chars:,} ký tự",
            f"Độ lệch số trang: {self.offset if self.offset is not None else 'chưa xác định'}",
            f"Số chương: {len(self.entries)}",
        ]
        for i, e in enumerate(self.entries, 1):
            span = f"trang {e.start}–{e.end} ({e.pages} trang)" if e.start is not None else f"trang in {e.printed_page}"
            lines.append(f"  {i:>2}. {e.title} – {span}")
        return "\n".join(lines)


def scan_window(total_pages: int) -> int:
    """Số trang dò ở mỗi đầu: 5 % tổng, tối thiểu 5, tối đa 20."""
    return min(WINDOW_MAX, max(WINDOW_MIN, math.ceil(total_pages * WINDOW_PCT)))


# Mỗi đoạn là một lượt gọi AI trích khái niệm. TreeBuilder cắt tối đa MAX_CHAPTER_CHARS = 12 000 ký tự/đoạn nhưng còn
# cắt theo tiêu đề "Chương/Bài/Phần" và theo ranh giới trang nên đoạn thật nhỏ hơn: đo trên giáo trình Cần Thơ
# (157 918 ký tự → 24 đoạn ≈ 6 600) và Lê Minh Hoàng (424 614 ký tự → 54 đoạn ≈ 7 900). Lấy 7 000.
CHARS_PER_CHUNK = 7_000
# Mức chi tiết GV chọn: số khái niệm tối đa AI được trích mỗi đoạn (max_concepts của TreeBuilder) và số nút TRUNG BÌNH
# mỗi đoạn. Đo thật (gpt-4o-mini, 3 đoạn đầu chương 1 của cả hai giáo trình): trần 4/8/12 ra 3,7/7,7–8,0/11,0 nút
# mỗi đoạn, tức AI gần như luôn lấp đầy trần. ponytail: đo với 1 model và 2 giáo trình, đo lại khi đổi model.
DETAIL_CAPS = {"SUMMARY": 4, "STANDARD": 8, "DETAILED": 12}
NODES_PER_CHUNK = {"SUMMARY": 4, "STANDARD": 8, "DETAILED": 11}
DEFAULT_DETAIL = "DETAILED"  # dựng tự động (giáo trình nhỏ) giữ nguyên hành vi cũ: trần 12 khái niệm / đoạn


@dataclass(frozen=True)
class SizeEstimate:
    chunks: int  # số lượt gọi AI trích khái niệm
    nodes: int  # số nút cây dự kiến
    llm_calls: int  # tổng lượt gọi AI: trích + tiên quyết (+ rubric) cho mỗi nút
    level: str  # "OK" | "WARN" | "TOO_LARGE"


def estimate_size(
    total_chars: int,
    n_chapters: int,
    warn_nodes: int,
    max_nodes: int,
    detail: str = DEFAULT_DETAIL,
    lazy_rubric: bool = False,
) -> SizeEstimate:
    """Ước cỡ công việc dựng cây, không tốn token. Tính theo ký tự (slide ít chữ nhiều trang không bị nói quá),
    số đoạn không ít hơn số chương vì mỗi chương được cắt riêng. `lazy_rubric`: bỏ N lượt sinh rubric."""
    chunks = max(n_chapters, math.ceil(total_chars / CHARS_PER_CHUNK)) if total_chars else 0
    nodes = chunks * NODES_PER_CHUNK[detail]
    level = "TOO_LARGE" if nodes >= max_nodes else "WARN" if nodes >= warn_nodes else "OK"
    return SizeEstimate(chunks, nodes, chunks + nodes + (0 if lazy_rubric else nodes), level)


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def _norm(s: str) -> str:
    """Bỏ dấu câu, hạ chữ thường, gộp khoảng trắng – để so tiêu đề mục lục với tiêu đề trong thân bài."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", _nfc(s).casefold())).strip()


def parse_toc_lines(text: str) -> list[tuple[str, int]]:
    """Các dòng dạng "tiêu đề …… số trang". Dòng chỉ có một từ mà không có chấm dẫn ("Chương 1") bị loại để
    khỏi nhầm số chương với số trang; tiêu đề kết thúc bằng dấu phẩy là dòng chỉ mục."""
    out = []
    for raw in text.splitlines():
        m = _LINE.match(_nfc(raw).strip())
        if not m:
            continue
        title = m["title"].strip(" .·…_-–\t")
        words = len(re.findall(r"[^\W\d_]+", title))
        if title.endswith(",") or words == 0 or (words < 2 and not _LEADER.search(m["sep"])):
            continue
        out.append((title, int(m["page"])))
    return out


def _ascending(lines: list[tuple[str, int]]) -> bool:
    if len(lines) < 2:
        return True
    ok = sum(b[1] >= a[1] for a, b in zip(lines, lines[1:], strict=False))
    return ok / (len(lines) - 1) >= MIN_ASCENDING


def _toc_runs(region: list[dict[str, Any]]) -> list[list[tuple[int, list[tuple[str, int]]]]]:
    """Chuỗi trang liền nhau là mục lục: [(số trang tệp, các dòng)]."""
    runs: list[list[tuple[int, list[tuple[str, int]]]]] = []
    cur: list[tuple[int, list[tuple[str, int]]]] = []
    for p in region:
        lines = parse_toc_lines(p["text"])
        follows = bool(cur) and p["number"] == cur[-1][0] + 1 and bool(lines) and lines[0][1] >= cur[-1][1][-1][1]
        ok = _ascending(lines) and len(lines) >= (2 if follows else MIN_LINES_PER_PAGE)
        if ok and (follows or not cur):
            cur.append((p["number"], lines))
            continue
        if cur:
            runs.append(cur)
        cur = [(p["number"], lines)] if ok else []
    if cur:
        runs.append(cur)
    return runs


def _top_level(entries: list[TocEntry]) -> tuple[list[TocEntry], bool]:
    """Chỉ giữ cấp chương: nhóm từ khóa "Chương/Chapter/Unit/Tuần…" có nhiều dòng nhất → mục đánh số "1." →
    mọi dòng không phải mục con "n.n". Trả (danh sách, chắc chắn?): hai cách đầu chắc chắn, cách cuối là đoán."""
    kw = Counter(m[1].casefold() for e in entries if (m := _HEAD.match(e.title)))
    if kw and kw.most_common(1)[0][1] >= MIN_CHAPTERS:
        top = kw.most_common(1)[0][0]
        return [e for e in entries if (m := _HEAD.match(e.title)) and m[1].casefold() == top], True
    numbered = [e for e in entries if _TOP_NUM.match(e.title)]
    if len(numbered) >= MIN_CHAPTERS:
        return numbered, True
    return [e for e in entries if not _SUB.match(e.title)], False


def _find_offset(entries: list[TocEntry], pages: list[dict[str, Any]], skip: set[int]) -> int | None:
    """Tìm trang tệp mà dòng đầu (hoặc 2–3 dòng đầu ghép lại) bắt đầu bằng tiêu đề chương ⇒ độ lệch. Lấy giá trị
    được nhiều chương cùng ra (≥ 2 phiếu); không đủ đồng thuận ⇒ None, không đoán."""
    cache: dict[int, list[str]] = {}

    def lines_of(p: dict[str, Any]) -> list[str]:
        if p["number"] not in cache:
            cache[p["number"]] = [n for ln in p["text"].splitlines() if (n := _norm(ln))]
        return cache[p["number"]]

    def opens(p: dict[str, Any], nt: str) -> bool:
        ls = lines_of(p)
        return any(" ".join(ls[i : i + k]).startswith(nt) for i in range(len(ls)) for k in (1, 2, 3))

    sample = entries[:CALIBRATE_N]
    votes: Counter[int] = Counter()
    for e in sample:
        nt = _norm(e.title)
        hit = next((p["number"] for p in pages if p["number"] not in skip and nt and opens(p, nt)), None)
        if hit is not None:
            votes[hit - e.printed_page] += 1
    if not votes:
        return None
    off, v = votes.most_common(1)[0]
    return off if v >= min(2, len(sample)) else None


def _assign_ranges(entries: list[TocEntry], offset: int, total: int, toc_pages: list[int]) -> None:
    for e in entries:
        e.start = min(max(e.printed_page + offset, 1), total)
    for cur, nxt in zip(entries, entries[1:], strict=False):
        cur.end = max(nxt.start - 1, cur.start)  # type: ignore[operator]
    last = entries[-1]
    back = min((t for t in toc_pages if t > last.start), default=total + 1) - 1  # type: ignore[operator]
    last.end = max(back, last.start)  # type: ignore[type-var]


def _from_bookmarks(bookmarks: list[tuple[int, str, int]], total: int) -> list[TocEntry]:
    """Cấp nhỏ nhất có ≥ MIN_CHAPTERS mục hợp lệ (bỏ mục trỏ ngoài tài liệu, vd. trang -1)."""
    valid = [(lvl, _nfc(t).strip(), p) for lvl, t, p in bookmarks if 1 <= p <= total and t.strip()]
    by_level = Counter(lvl for lvl, _, _ in valid)
    level = next((lv for lv in sorted(by_level) if by_level[lv] >= MIN_CHAPTERS), None)
    return [TocEntry(t, p, start=p) for lvl, t, p in valid if lvl == level] if level is not None else []


def find_toc(pages: list[dict[str, Any]], bookmarks: list[tuple[int, str, int]] | None = None) -> TocResult:
    total = len(pages)
    res = TocResult("none", total_pages=total, total_chars=sum(len(re.sub(r"\s", "", p["text"])) for p in pages))
    if total == 0:
        return res

    entries = _from_bookmarks(bookmarks or [], total)
    if len(entries) >= MIN_CHAPTERS:
        _assign_ranges(entries, 0, total, [])  # tính trang cuối trên danh sách đầy đủ, rồi mới bỏ mục không phải chương
        chapters, certain = _top_level(entries)
        if len(chapters) < MIN_CHAPTERS:
            chapters, certain = entries, False
        return TocResult("bookmark", chapters, [], 0, res.total_pages, res.total_chars, not certain)

    w = scan_window(total)
    region = [p for p in pages if p["number"] <= w or p["number"] > total - w]
    runs = _toc_runs(region)
    if not runs:
        return res
    best = max(runs, key=lambda r: sum(len(ls) for _, ls in r))  # mục lục thật: nhiều dòng nhất
    toc_pages = [n for n, _ in best]
    raw = [TocEntry(t, p) for _, ls in best for t, p in ls]
    chapters, certain = _top_level(raw)
    if len(chapters) < MIN_CHAPTERS:
        return res

    res.source, res.entries, res.toc_pages, res.ambiguous = "toc_pages", chapters, toc_pages, not certain
    res.offset = _find_offset(chapters, pages, set(toc_pages))
    if res.offset is not None:
        _assign_ranges(chapters, res.offset, total, toc_pages)
    return res


def main(path: str) -> None:
    import pymupdf  # chỉ cần khi chạy tay; hàm find_toc không phụ thuộc

    with pymupdf.open(path) as doc:
        pages = [{"number": i, "text": p.get_text("text"), "headings": []} for i, p in enumerate(doc, 1)]
        marks = [(lvl, title, page) for lvl, title, page in (x[:3] for x in doc.get_toc())]
    # ponytail: chưa OCR – PDF scan sẽ ra "không tìm thấy"; luồng thật dùng pages.json đã OCR của C1-09
    print(find_toc(pages, marks).summary())


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Cách dùng: uv run python -m app.services.syllabus_toc <giaotrinh.pdf>")
    main(sys.argv[1])
