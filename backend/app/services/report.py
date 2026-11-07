"""Báo cáo lớp CSV / PDF cho GV (FR-HM-10). Chủ: Long (C2-20).

Số liệu lấy từ `HeatmapService.snapshot` – cùng nguồn với màn bản đồ nhiệt nên báo cáo luôn khớp màn hình.
CSV (UTF-8 có BOM để Excel đọc đúng tiếng Việt): lưới SV × nút kèm 3 dòng tổng kết theo nút. PDF: tổng quan lớp,
bảng nút (đã thử / Đạt / màu bằng chữ), cảnh báo điểm nghẽn, tiến độ từng SV. Màu luôn đi kèm chữ.
"""

import csv
import html
import io
import re
import unicodedata
from datetime import datetime
from typing import TYPE_CHECKING, Literal
from uuid import UUID

import pymupdf
from sqlalchemy.orm import Session

from app.models.schemas.heatmap import HeatmapSnapshot
from app.services.classes import ClassService
from app.services.heatmap import HeatmapService

if TYPE_CHECKING:
    from app.api.deps import CurrentUser

ReportFormat = Literal["csv", "pdf"]

STATE_LABEL = {
    "MASTERED": "Đạt",
    "NOT_PASSED": "Chưa đạt",
    "IN_PROGRESS": "Đang giảng",
    "AVAILABLE": "Sẵn sàng",
    "LOCKED": "Khóa",
    "NEEDS_REVERIFY": "Cần xác nhận lại",
}
COLOR_LABEL = {
    "GREEN": "Xanh – tốt",
    "YELLOW": "Vàng – cần chú ý",
    "RED": "Đỏ – điểm nghẽn",
    "GREY": "Xám – chưa đủ mẫu",
}
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value: str) -> str:
    """Chặn CSV injection: ô văn bản bắt đầu bằng ký tự công thức thì thêm dấu nháy đơn để Excel không chạy nó."""
    return "'" + value if value.startswith(_FORMULA_START) else value


def slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.replace("đ", "d").replace("Đ", "D"))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower() or "lop"


def _pct(rate: float | None) -> str:
    return "" if rate is None else str(round(rate * 100))


class ReportService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def build(
        self, class_id: UUID, user: "CurrentUser", fmt: ReportFormat, now: datetime | None = None
    ) -> tuple[bytes, str, str]:
        """(nội dung, media type, tên tệp). Chỉ GV phụ trách lớp; lớp chưa phát hành cây ⇒ 404 TREE_NOT_PUBLISHED."""
        heat = HeatmapService(self.db)
        heat.require_owner(class_id, user)
        snap = heat.snapshot(class_id)
        cls = ClassService(self.db).info(class_id)
        stamp = (now or datetime.now()).strftime("%Y%m%d")
        base = f"bao-cao-{slug(cls.name)}-{stamp}"
        title = f"{cls.name} – {cls.semester}"
        if fmt == "csv":
            return self._csv(snap), "text/csv; charset=utf-8", f"{base}.csv"
        return self._pdf(snap, title, stamp), "application/pdf", f"{base}.pdf"

    # ------------------------------------------------------------------ CSV

    @staticmethod
    def _csv(snap: HeatmapSnapshot) -> bytes:
        nodes = snap.tree.nodes if snap.tree else []
        stats = {n.node_key: n for n in snap.nodes}
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(["MSSV", "Họ tên", "Số nút Đạt", "Tiến độ (%)", *[n.code or n.key for n in nodes]])
        for r in snap.grid:
            w.writerow(
                [
                    safe_cell(r.student_code),
                    safe_cell(r.student_name),
                    r.mastered_count,
                    round(r.progress * 100),
                    *[STATE_LABEL.get(r.states_by_key.get(n.key, ""), "") for n in nodes],
                ]
            )
        pad = ["", "", ""]
        w.writerow(["", "Đã thử", *pad[1:], *[stats[n.key].attempted_count for n in nodes]])
        w.writerow(["", "Đạt", *pad[1:], *[stats[n.key].passed_count for n in nodes]])
        w.writerow(["", "Tỉ lệ Đạt (%)", *pad[1:], *[_pct(stats[n.key].pass_rate) for n in nodes]])
        return b"\xef\xbb\xbf" + out.getvalue().encode("utf-8")

    # ------------------------------------------------------------------ PDF

    @staticmethod
    def _pdf(snap: HeatmapSnapshot, title: str, stamp: str) -> bytes:
        e = html.escape
        node_rows = "".join(
            f"<tr><td>{e(n.code)}</td><td>{e(n.title)}</td><td>{n.passed_count}/{n.attempted_count}</td>"
            f"<td>{_pct(n.pass_rate) + '%' if n.pass_rate is not None else '–'}</td>"
            f"<td>{e(COLOR_LABEL[n.color.value])}</td></tr>"
            for n in snap.nodes
        )
        alerts = "".join(f"<li>{e(a.message)}</li>" for a in snap.alerts) or "<li>Không có điểm nghẽn.</li>"
        total = len(snap.nodes)
        student_rows = "".join(
            f"<tr><td>{e(r.student_code)}</td><td>{e(r.student_name)}</td>"
            f"<td>{r.mastered_count}/{total}</td><td>{round(r.progress * 100)}%</td></tr>"
            for r in snap.grid
        )
        doc = f"""
        <h2>Báo cáo lớp {e(title)}</h2>
        <p>Ngày {stamp[6:]}/{stamp[4:6]}/{stamp[:4]} · Sĩ số {snap.enrolled_count} sinh viên</p>
        <h3>Cảnh báo</h3><ul>{alerts}</ul>
        <h3>Theo nút kỹ năng</h3>
        <table>
        <tr><th>Nút</th><th>Tên</th><th>Đạt/Đã thử</th><th>Tỉ lệ Đạt</th><th>Trạng thái</th></tr>{node_rows}
        </table>
        <h3>Theo sinh viên</h3>
        <table>
        <tr><th>MSSV</th><th>Họ tên</th><th>Nút Đạt</th><th>Tiến độ</th></tr>{student_rows}
        </table>
        """
        css = (
            "table{border-collapse:collapse;width:100%}"
            "th,td{border:1px solid #888;padding:2px 4px;font-size:9pt}th{background:#eee}"
        )
        story = pymupdf.Story(html=doc, user_css=css)
        buf = io.BytesIO()
        writer = pymupdf.DocumentWriter(buf)
        page = pymupdf.paper_rect("a4")
        where = page + (36, 36, -36, -36)
        more = True
        while more:
            dev = writer.begin_page(page)
            more, _ = story.place(where)
            story.draw(dev)
            writer.end_page()
        writer.close()
        return buf.getvalue()
