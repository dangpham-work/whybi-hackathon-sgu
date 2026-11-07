"""Bản đồ nhiệt lớp học – MX3, FR-HM-01…10. Chủ: Long (C2-11…C2-13, C2-17, C2-20)."""

from uuid import UUID

from fastapi import APIRouter

from app.api.deps import CurrentUser, Lecturer
from app.core.errors import NotImplementedYet
from app.models.enums import HeatColor, MasteryState
from app.models.schemas.common import ApiModel
from app.models.schemas.mastery import HeatmapAlert

router = APIRouter(tags=["heatmap"])


class NodeStat(ApiModel):
    node_id: UUID
    code: str
    title: str
    color: HeatColor
    pass_rate: float | None
    attempted_count: int
    passed_count: int
    is_root_cause: bool = False


class GridRow(ApiModel):
    student_id: UUID
    student_name: str
    student_code: str
    states: dict[str, MasteryState]  # node_id → trạng thái
    progress: float


class HeatmapSnapshot(ApiModel):
    class_id: UUID
    enrolled_count: int
    online_count: int = 0
    active_sessions: int = 0
    nodes: list[NodeStat]
    grid: list[GridRow]
    alerts: list[HeatmapAlert] = []


class NodeDetail(ApiModel):
    node_id: UUID
    stat: NodeStat
    students_by_state: dict[str, list[GridRow]]
    top_misconceptions: list[dict]
    root_cause_node_id: UUID | None = None


class ClassSettings(ApiModel):
    """GV-10 – FR-HM-08 (BR-03, BR-06)."""

    pass_threshold: int = 70
    green_threshold: float = 0.7
    yellow_threshold: float = 0.4
    min_sample: int = 5
    challenge_count: int = 3


@router.get("/classes/{class_id}/heatmap", response_model=HeatmapSnapshot)
def get_heatmap(class_id: UUID, user: CurrentUser = Lecturer) -> HeatmapSnapshot:
    """Ảnh chụp: cây màu + lưới SV × Nút có tên; sau đó nghe kênh class:{id}:heatmap."""
    raise NotImplementedYet("C2-13")


@router.get("/classes/{class_id}/nodes/{node_id}/detail", response_model=NodeDetail)
def node_detail(class_id: UUID, node_id: UUID, user: CurrentUser = Lecturer) -> NodeDetail:
    raise NotImplementedYet("C2-13")


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
