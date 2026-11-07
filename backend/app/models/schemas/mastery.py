"""Sự kiện nội bộ trên bus Redis Pub/Sub (mục 3.2 kế hoạch, mục 5.1.3 đề cương) và hợp đồng ma trận thành thạo.
Chủ: Long (C2-05, C2-10).

session (Đăng) ─ session.completed(SessionResult) ─▶ mastery (Long) ─ mastery.changed ─▶ heatmap, matching

Mã lỗi khi SV bắt đầu phiên (MasteryService.start_session – C1-07 của Đăng gọi; Bảng 4.8, BR-02, BR-11):
- 409 NODE_LOCKED          details {missingPrerequisites: [key…]}  – còn tiên quyết chưa Đạt
- 409 RETRY_COOLDOWN       details {retryAt: ISO-8601}            – vừa Chưa đạt, chờ 10 phút (BR-11)
- 409 NODE_ALREADY_MASTERED – nút đã Đạt (chỉ học lại khi NEEDS_REVERIFY)
- 409 SESSION_IN_PROGRESS  details {sessionId}                    – đang có phiên chưa xong ở nút này
- 403 NOT_ENROLLED · 404 NODE_NOT_FOUND · 404 TREE_NOT_PUBLISHED
"""

from datetime import UTC, datetime
from uuid import UUID

from pydantic import Field

from app.models.enums import HeatColor, MasteryChangeReason, MasteryState
from app.models.schemas.common import ApiModel
from app.models.schemas.tree import TreeVersion

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
    reason: MasteryChangeReason | None = None  # C2-10; None = nguồn cũ chưa ghi lý do
    version_id: UUID | None = None  # phiên bản cây chứa node_id (C2-10)


# --- Bản đồ học tập cá nhân: GET /classes/{classId}/my-map (FR-TB-01, FR-TB-02 – màn SV-02, SV-03) ---

RETRY_COOLDOWN_MINUTES = 10  # BR-11


class NodeProgress(ApiModel):
    """Một ô của SV: trạng thái + đủ dữ liệu cho SV-03 Chi tiết nút."""

    node_id: UUID
    node_key: str
    state: MasteryState
    best_score: float | None = None  # 0–100, None = chưa có lượt chấm
    attempts: int = 0  # số lượt đã chấm
    missing_prerequisites: list[str] = []  # key tiên quyết chưa Đạt (chỉ khác rỗng khi LOCKED)
    retry_at: datetime | None = None  # NOT_PASSED: thời điểm được thử lại (BR-11); None = thử được ngay
    can_start: bool = False  # SV bấm "Bắt đầu giảng" được ngay bây giờ
    last_session_id: UUID | None = None
    updated_at: datetime | None = None


class MyMap(ApiModel):
    """Cây đang phát hành + trạng thái từng nút của SV. `tree` dùng thẳng cho SkillTree (mode="learner"),
    `progress` tra theo `nodeKey` để tô màu (frontend/src/lib/status.ts)."""

    class_id: UUID
    student_id: UUID
    tree: TreeVersion
    progress: list[NodeProgress]
    frontier: list[str] = []  # key nút nên học tiếp: chưa Đạt nhưng mọi tiên quyết đã Đạt (mục 2.2.1)
    mastered_count: int = 0
    total_count: int = 0


class StartCheck(ApiModel):
    """Kết quả kiểm tra không ném lỗi (MasteryService.can_start) – `code` trùng mã lỗi của start_session."""

    allowed: bool
    code: str | None = None
    state: MasteryState | None = None
    missing_prerequisites: list[str] = []
    retry_at: datetime | None = None


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
