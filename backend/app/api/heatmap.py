"""Bản đồ nhiệt lớp học – MX3, FR-HM-01…10. Chủ: Long (C2-11…C2-13, C2-17, C2-20)."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, Lecturer
from app.core.errors import NotImplementedYet
from app.db.session import get_db
from app.models.schemas.common import ApiModel
from app.models.schemas.heatmap import GridRow, HeatmapSnapshot, NodeDetail, NodeStat
from app.services.heatmap import HeatmapService

__all__ = ["GridRow", "HeatmapSnapshot", "NodeDetail", "NodeStat", "router"]

router = APIRouter(tags=["heatmap"])


class ClassSettings(ApiModel):
    """GV-10 – FR-HM-08 (BR-03, BR-06)."""

    pass_threshold: int = 70
    green_threshold: float = 0.7
    yellow_threshold: float = 0.4
    min_sample: int = 5
    challenge_count: int = 3


@router.get("/classes/{class_id}/heatmap", response_model=HeatmapSnapshot)
def get_heatmap(class_id: UUID, user: CurrentUser = Lecturer, db: Session = Depends(get_db)) -> HeatmapSnapshot:
    """Ảnh chụp: cây màu + lưới SV × Nút có tên; sau đó nghe kênh class:{id}:heatmap (FR-HM-01, 02, 04, 05).
    Chỉ GV phụ trách lớp: 404 CLASS_NOT_FOUND / 403 NOT_CLASS_OWNER / 404 TREE_NOT_PUBLISHED."""
    svc = HeatmapService(db)
    svc.require_owner(class_id, user)
    return svc.snapshot(class_id)


@router.get("/classes/{class_id}/nodes/{node_id}/detail", response_model=NodeDetail)
def node_detail(
    class_id: UUID, node_id: UUID, user: CurrentUser = Lecturer, db: Session = Depends(get_db)
) -> NodeDetail:
    """GV-06 (FR-HM-06): SV theo trạng thái (có tên), quan niệm sai phổ biến, nút gốc.
    Nút không thuộc bản đang phát hành của lớp ⇒ 404 NODE_NOT_FOUND."""
    svc = HeatmapService(db)
    svc.require_owner(class_id, user)
    return svc.node_detail(class_id, node_id)


@router.get("/classes/{class_id}/students/{student_id}/profile")
def student_profile(class_id: UUID, student_id: UUID, user: CurrentUser = Lecturer) -> dict:
    """GV-07 / GV-08: hồ sơ năng lực, transcript, ghi âm (FR-HM-07)."""
    raise NotImplementedYet("C2-17")


@router.put("/classes/{class_id}/settings", response_model=ClassSettings)
def put_settings(class_id: UUID, body: ClassSettings, user: CurrentUser = Lecturer) -> ClassSettings:
    raise NotImplementedYet("C2-17")


@router.get("/classes/{class_id}/report")
def export_report(class_id: UUID, format: str = "csv", user: CurrentUser = Lecturer) -> dict:
    """Xuất báo cáo lớp CSV / PDF (FR-HM-10, vòng 3)."""
    raise NotImplementedYet("C2-20")
