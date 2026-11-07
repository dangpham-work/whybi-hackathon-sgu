"""Ảnh chụp bản đồ nhiệt cho GV-05 / GV-06 (FR-HM-01, 02, 04, 05, 06). Chủ: Long (C2-13).

Trước C2-13 các lớp này nằm trong `app/api/heatmap.py` (vẫn import lại ở đó, tên schema OpenAPI giữ nguyên).
C2-13 chỉ THÊM trường tùy chọn – tương thích ngược với kiểu frontend đã sinh.
Frontend tô màu theo `nodeKey` (SkillTree `heat`), lưới tra `statesByKey`.
"""

from uuid import UUID

from app.models.enums import HeatColor, HeatSample, MasteryState
from app.models.schemas.common import ApiModel
from app.models.schemas.mastery import HeatmapAlert
from app.models.schemas.tree import TreeVersion


class NodeStat(ApiModel):
    node_id: UUID
    code: str
    title: str
    color: HeatColor
    pass_rate: float | None
    attempted_count: int
    passed_count: int
    is_root_cause: bool = False  # nút này là gốc X của ít nhất một cảnh báo
    node_key: str | None = None  # C2-13
    attempted_rate: float | None = None  # C2-13: đã thử / sĩ số
    enrolled_count: int | None = None  # C2-13
    sample: HeatSample | None = None  # C2-13: NO_ATTEMPT / INSUFFICIENT / SUFFICIENT (FR-HM-04)
    label: str | None = None  # C2-13: chữ đi kèm màu, vd. "✗ Điểm nghẽn – 2/9 Đạt"
    root_cause_node_id: UUID | None = None  # C2-13: nút nên giảng lại trước (khi nút này ĐỎ)
    root_cause_node_key: str | None = None  # C2-13


class GridRow(ApiModel):
    student_id: UUID
    student_name: str
    student_code: str
    states: dict[str, MasteryState]  # node_id → trạng thái (SV chưa có ô ở nút thì không có mục)
    progress: float  # số nút Đạt / tổng số nút, 0–1
    states_by_key: dict[str, MasteryState] = {}  # C2-13: node_key → trạng thái
    mastered_count: int = 0  # C2-13: số nút Đạt (MASTERED / NEEDS_REVERIFY)


class HeatmapSnapshot(ApiModel):
    class_id: UUID
    enrolled_count: int
    online_count: int = 0
    active_sessions: int = 0  # số ô IN_PROGRESS
    nodes: list[NodeStat]
    grid: list[GridRow]
    alerts: list[HeatmapAlert] = []
    tree: TreeVersion | None = None  # C2-13: cây đang phát hành – truyền thẳng cho SkillTree mode="heatmap"


class NodeDetail(ApiModel):
    node_id: UUID
    stat: NodeStat
    students_by_state: dict[str, list[GridRow]]  # MasteryState → SV (có tên) ở trạng thái đó tại nút này
    top_misconceptions: list[dict]
    root_cause_node_id: UUID | None = None
    node_key: str | None = None  # C2-13
    alert: HeatmapAlert | None = None  # C2-13: "Nên giảng lại X" khi nút này ĐỎ
