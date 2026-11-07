"""Sự kiện nội bộ trên bus Redis Pub/Sub (mục 3.2 kế hoạch, mục 5.1.3 đề cương). Chủ: Long (C2-05).

session (Đăng) ─ session.completed(SessionResult) ─▶ mastery (Long) ─ mastery.changed ─▶ heatmap, matching
"""

from datetime import UTC, datetime
from uuid import UUID

from pydantic import Field

from app.models.enums import HeatColor, MasteryState
from app.models.schemas.common import ApiModel

TOPIC_SESSION_COMPLETED = "session.completed"
TOPIC_MASTERY_CHANGED = "mastery.changed"


class MasteryChanged(ApiModel):
    """Payload `mastery.changed` (C2-05, đã chốt). Chỉ MasteryService phát; heatmap (C2-11), matching (C2-14) nghe."""

    class_id: UUID
    student_id: UUID
    node_id: UUID
    node_key: str | None = None  # key ổn định giữa các phiên bản – frontend tô màu theo key
    old_state: MasteryState | None  # None = ô vừa được khởi tạo
    new_state: MasteryState
    unlocked_node_ids: list[UUID] = []  # nút chuyển LOCKED → AVAILABLE nhờ thay đổi này
    session_id: UUID | None = None  # phiên gây ra thay đổi (None khi do phát hành phiên bản mới)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# --- Payload WebSocket theo Bảng 5.11 ---


class HeatmapCell(ApiModel):
    """class:{id}:heatmap → heatmap.cell"""

    student_id: UUID
    student_name: str
    node_id: UUID
    state: MasteryState


class HeatmapNode(ApiModel):
    """class:{id}:heatmap → heatmap.node"""

    node_id: UUID
    color: HeatColor
    pass_rate: float | None
    attempted_rate: float


class HeatmapAlert(ApiModel):
    """class:{id}:heatmap → heatmap.alert ("Nên giảng lại X")"""

    node_id: UUID
    root_cause_node_id: UUID
    message: str


class JobProgress(ApiModel):
    """job:{jobId} → job.progress"""

    percent: int
    step: str
