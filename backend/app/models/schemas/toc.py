"""Báo cáo mục lục & cỡ giáo trình gửi GV trước khi dựng cây (GET /classes/{id}/syllabi/{docId}/toc).

Danh sách chương do `services/syllabus_toc.py` trích (không tốn token); lời cảnh báo do AI viết từ danh sách đó
(`ai/agents/toc_advisor.py`) hoặc là câu mẫu khi không có mục lục / AI lỗi (`ai_written=False`).
"""

from typing import Literal

from pydantic import Field

from app.models.schemas.common import ApiModel

DetailLevel = Literal["SUMMARY", "STANDARD", "DETAILED"]  # Tóm lược ≤4 / Chuẩn ≤8 / Chi tiết ≤12 khái niệm mỗi đoạn


class TocChapter(ApiModel):
    index: int  # thứ tự chương, bắt đầu từ 1 – GV chọn chương theo số này
    title: str
    start_page: int | None = None  # trang đầu trong tệp; None khi chưa xác định được độ lệch số trang
    end_page: int | None = None
    pages: int | None = None
    chars: int = 0  # ký tự (không tính khoảng trắng) trong chương – để giao diện ước tính lại khi GV chọn chương


class TocSkip(ApiModel):
    index: int
    reason: str = Field(max_length=300)


class TocAdvice(ApiModel):
    message: str = Field(max_length=800)
    keep: list[int] = []  # chương AI đề xuất giữ
    skip: list[TocSkip] = []  # chương AI đề xuất bỏ (mục lục, phụ lục, bài tập…) kèm lý do
    suggest_split: bool = False  # nên tách thành nhiều đợt / nhiều tệp


class BuildTreeRequest(ApiModel):
    ranges: list[list[int]] = []  # các khoảng trang [từ, đến] GV chọn (trang trong tệp); rỗng ⇒ toàn bộ tài liệu
    detail: DetailLevel = "STANDARD"  # mức chi tiết: giới hạn số khái niệm AI trích mỗi đoạn
    lazy_rubric: bool = False  # True ⇒ chưa sinh rubric lúc dựng cây; GV cắt tỉa cây rồi sinh một lượt ở trình sửa cây


class FillRubricsAccepted(ApiModel):
    missing: int  # số nút chưa có rubric đã được xếp hàng sinh (0 ⇒ không có việc gì để làm)


class JobCancelledOut(ApiModel):
    document_id: str
    status: str = "CANCELLED"


class TocReport(ApiModel):
    document_id: str
    source: str  # "bookmark" | "toc_pages" | "none"
    total_pages: int
    total_chars: int
    offset: int | None = None
    toc_pages: list[int] = []
    level: str  # "OK" | "WARN" | "TOO_LARGE"
    est_nodes: int
    est_calls: int
    # Hằng số công thức ước tính (lấy từ backend để giao diện tính lại đúng khi GV đổi lựa chọn)
    chars_per_chunk: int = 12000
    nodes_per_chunk: dict[str, int] = {}  # theo mức chi tiết
    detail_caps: dict[str, int] = {}  # số khái niệm tối đa mỗi đoạn theo mức chi tiết
    chapters: list[TocChapter] = []
    advice: TocAdvice
    ai_written: bool = False
    gated: bool = False  # True ⇒ đang chờ GV chọn chương rồi bấm dựng cây
