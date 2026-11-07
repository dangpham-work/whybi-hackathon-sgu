"""Bản đồ nhiệt lớp học – MX3, FR-HM-01…10. Chủ: Long (C2-11…C2-13, C2-17, C2-20)."""

from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, Lecturer, LecturerOrStudent
from app.db.session import get_db
from app.models.schemas.heatmap import ClassSettings, GridRow, HeatmapSnapshot, NodeDetail, NodeStat, StudentProfile
from app.services.classes import ClassService
from app.services.heatmap import HeatmapService
from app.services.report import ReportFormat, ReportService
from app.services.session_history import SessionHistoryService

__all__ = ["ClassSettings", "GridRow", "HeatmapSnapshot", "NodeDetail", "NodeStat", "StudentProfile", "router"]

router = APIRouter(tags=["heatmap"])


@router.get("/classes/{class_id}/heatmap", response_model=HeatmapSnapshot)
def get_heatmap(
    class_id: UUID,
    q: str | None = None,
    anonymize: bool = False,
    user: CurrentUser = Lecturer,
    db: Session = Depends(get_db),
) -> HeatmapSnapshot:
    """Ảnh chụp: cây màu + lưới SV × Nút có tên; sau đó nghe kênh class:{id}:heatmap (FR-HM-01, 02, 04, 05).
    `q` lọc lưới theo tên / MSSV; `anonymize=true` là chế độ trình chiếu (FR-HM-09).
    Chỉ GV phụ trách lớp: 404 CLASS_NOT_FOUND / 403 NOT_CLASS_OWNER / 404 TREE_NOT_PUBLISHED."""
    svc = HeatmapService(db)
    svc.require_owner(class_id, user)
    return svc.snapshot(class_id, q, anonymize)


@router.get("/classes/{class_id}/nodes/{node_id}/detail", response_model=NodeDetail)
def node_detail(
    class_id: UUID, node_id: UUID, anonymize: bool = False, user: CurrentUser = Lecturer, db: Session = Depends(get_db)
) -> NodeDetail:
    """GV-06 (FR-HM-06): SV theo trạng thái (có tên), quan niệm sai phổ biến, nút gốc.
    Nút không thuộc bản đang phát hành của lớp ⇒ 404 NODE_NOT_FOUND."""
    svc = HeatmapService(db)
    svc.require_owner(class_id, user)
    return svc.node_detail(class_id, node_id, anonymize)


@router.get("/classes/{class_id}/students/{student_id}/profile", response_model=StudentProfile)
def student_profile(
    class_id: UUID, student_id: UUID, user: CurrentUser = Lecturer, db: Session = Depends(get_db)
) -> StudentProfile:
    """GV-07 / GV-08: hồ sơ năng lực, transcript, ghi âm (FR-HM-07). Ghi âm nghe qua `GET /turns/{id}/audio`.
    Lỗi: 403 NOT_CLASS_OWNER, 403 NOT_ENROLLED (SV không ở lớp)."""
    return SessionHistoryService(db).student_profile(class_id, student_id, user)


@router.get("/turns/{turn_id}/audio", response_class=Response, responses={200: {"content": {"audio/*": {}}}})
def turn_audio(turn_id: UUID, user: CurrentUser = LecturerOrStudent, db: Session = Depends(get_db)) -> Response:
    """Nghe lại ghi âm một lượt (FR-HM-07, FR-TB-15): chính SV chủ phiên hoặc GV phụ trách lớp.
    404 AUDIO_NOT_AVAILABLE khi SV không đồng ý lưu hoặc ghi âm đã quá hạn; 403 với người khác."""
    data, content_type = SessionHistoryService(db).audio_for_turn(turn_id, user)
    return Response(data, media_type=content_type, headers={"Cache-Control": "private, no-store"})


@router.get("/classes/{class_id}/settings", response_model=ClassSettings)
def get_settings(class_id: UUID, user: CurrentUser = Lecturer, db: Session = Depends(get_db)) -> ClassSettings:
    """GV-10: cấu hình hiện tại của lớp (FR-HM-08)."""
    HeatmapService(db).require_owner(class_id, user)
    return ClassService(db).get_settings(class_id)


@router.put("/classes/{class_id}/settings", response_model=ClassSettings)
def put_settings(
    class_id: UUID, body: ClassSettings, user: CurrentUser = Lecturer, db: Session = Depends(get_db)
) -> ClassSettings:
    """GV-10 (FR-HM-08): lưu ngưỡng màu, cỡ mẫu tối thiểu, ngưỡng Đạt, số câu phản biện; màu cả lớp tính lại ngay và
    đẩy lên kênh heatmap. 422 khi ngưỡng vàng cao hơn ngưỡng xanh hoặc số câu ngoài 3–5."""
    return HeatmapService(db).update_settings(class_id, user, body)


@router.get("/classes/{class_id}/report", response_class=Response)
def export_report(
    class_id: UUID,
    format: ReportFormat = "csv",
    user: CurrentUser = Lecturer,
    db: Session = Depends(get_db),
) -> Response:
    """Xuất báo cáo lớp CSV (lưới SV × nút) hoặc PDF (tổng quan, nút, cảnh báo, SV) – FR-HM-10. Tải về dạng tệp.
    Chỉ GV phụ trách lớp (403 NOT_CLASS_OWNER); lớp chưa phát hành cây ⇒ 404 TREE_NOT_PUBLISHED."""
    data, media_type, filename = ReportService(db).build(class_id, user, format)
    return Response(
        data,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "private, no-store"},
    )
