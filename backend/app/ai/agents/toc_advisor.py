"""Viết cảnh báo cỡ giáo trình cho GV từ mục lục đã trích (không đọc nội dung giáo trình). Chủ: Đăng.

AI chỉ nhận danh sách chương + số trang + số liệu cỡ (khoảng vài trăm token) và được báo rõ danh sách do chương trình
tự trích. Việc dừng hay chạy do Python quyết theo ngưỡng (`estimate_size`), AI chỉ viết lời cảnh báo và đề xuất
chương nên giữ / bỏ. AI lỗi hoặc không có mục lục ⇒ câu mẫu, không chặn luồng.
"""

import logging
from typing import Literal

from pydantic import BaseModel

from app.ai.gateway import LLMGateway
from app.ai.prompts import render_prompt, wrap_student_text
from app.core.errors import AppError
from app.models.schemas.toc import TocAdvice, TocSkip
from app.services.syllabus_toc import SizeEstimate, TocResult

log = logging.getLogger(__name__)

SOURCE_NOTE = {
    "bookmark": "bookmark (mục lục nhúng sẵn) của tệp",
    "toc_pages": "các trang mục lục in trong sách",
}
MAX_MESSAGE, MAX_REASON = 800, 300


class _SkipDraft(BaseModel):
    index: int
    reason: str = ""


class TocAdviceDraft(BaseModel):
    message: str
    keep: list[int] = []
    skip: list[_SkipDraft] = []
    suggest_split: bool = False


class _Label(BaseModel):
    index: int
    kind: Literal["CHAPTER", "FRONT", "BACK"]


class TocLabels(BaseModel):
    labels: list[_Label] = []


def classify_chapters(gw: LLMGateway, res: TocResult) -> bool:
    """Mục lục không có từ khóa "Chương n" (res.ambiguous): nhờ AI gán nhãn từng mục, bỏ tên sách / tổng quan (FRONT)
    và phụ lục (BACK). Mục AI không nhắc tới coi là CHAPTER; còn dưới 2 chương hoặc AI lỗi ⇒ giữ nguyên danh sách.
    Trang cuối các chương đã tính trên danh sách đầy đủ nên chương đứng trước phụ lục vẫn kết thúc đúng chỗ."""
    system = render_prompt(
        "toc_classify",
        source_note=SOURCE_NOTE.get(res.source, "mục lục của tệp"),
        total_pages=str(res.total_pages),
    )
    msgs = [
        {"role": "system", "content": system},
        {"role": "user", "content": wrap_student_text(_listing(res), "toc_data")},
    ]
    try:
        labels = gw.call_json(TocLabels, msgs)
    except AppError as exc:
        log.warning("AI không phân loại được mục lục (%s), giữ nguyên danh sách", exc.code)
        return False
    kind = {lb.index: lb.kind for lb in labels.labels}
    kept = [e for i, e in enumerate(res.entries, 1) if kind.get(i, "CHAPTER") == "CHAPTER"]
    if len(kept) < 2:
        return False
    res.entries, res.ambiguous = kept, False
    return True


def _listing(res: TocResult) -> str:
    out = []
    for i, e in enumerate(res.entries, 1):
        span = f"trang {e.start}–{e.end} ({e.pages} trang)" if e.start is not None else "chưa rõ trang trong tệp"
        out.append(f"{i}. {e.title} – {span}")
    return "\n".join(out)


def template_advice(res: TocResult, est: SizeEstimate) -> TocAdvice:
    """Câu mẫu (không AI) khi không có mục lục hoặc AI lỗi."""
    size = f"Giáo trình {res.total_pages} trang (~{res.total_chars:,} ký tự) dự kiến cho ra khoảng {est.nodes} nút"
    cost = f"và tốn khoảng {est.llm_calls} lượt gọi AI."
    if res.entries:
        how = f"Hệ thống tìm thấy {len(res.entries)} chương; thầy/cô nên chỉ chọn các chương trọng tâm để dựng cây."
    else:
        how = "Không tìm thấy mục lục trong tệp; thầy/cô nên nhập khoảng trang trọng tâm hoặc tách thành nhiều tệp nhỏ."
    return TocAdvice(message=f"{size} {cost} {how}", suggest_split=est.level == "TOO_LARGE")


def _clean(draft: TocAdviceDraft, n: int) -> TocAdvice:
    """Bỏ chỉ số ngoài danh sách / trùng; chương vừa giữ vừa bỏ thì theo `skip`."""
    skip, seen = [], set()
    for s in draft.skip:
        if 1 <= s.index <= n and s.index not in seen:
            seen.add(s.index)
            skip.append(TocSkip(index=s.index, reason=s.reason[:MAX_REASON]))
    keep = sorted({k for k in draft.keep if 1 <= k <= n} - seen)
    return TocAdvice(message=draft.message[:MAX_MESSAGE], keep=keep, skip=skip, suggest_split=draft.suggest_split)


def advise(gw: LLMGateway, res: TocResult, est: SizeEstimate, warn_nodes: int) -> tuple[TocAdvice, bool]:
    """Trả (lời cảnh báo, do AI viết?)."""
    if not res.entries:
        return template_advice(res, est), False  # không có gì để AI đọc
    system = render_prompt(
        "toc_advice",
        level=est.level,
        source_note=SOURCE_NOTE.get(res.source, "mục lục của tệp"),
        total_pages=str(res.total_pages),
        total_chars=f"{res.total_chars:,}",
        est_nodes=str(est.nodes),
        est_calls=str(est.llm_calls),
        warn_nodes=str(warn_nodes),
    )
    msgs = [
        {"role": "system", "content": system},
        {"role": "user", "content": wrap_student_text(_listing(res), "toc_data")},
    ]
    try:
        draft = gw.call_json(TocAdviceDraft, msgs)
    except AppError as exc:
        log.warning("AI không viết được cảnh báo mục lục (%s), dùng câu mẫu", exc.code)
        return template_advice(res, est), False
    return _clean(draft, len(res.entries)), True
