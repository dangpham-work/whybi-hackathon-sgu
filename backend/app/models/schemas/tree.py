"""HỢP ĐỒNG DỮ LIỆU #1 – cây kỹ năng (Bảng 7 kế hoạch phân công).
Người chốt: Long (C2-02, đã chốt) · Bên dùng: Đăng, Thắng, Quyền · Hạn: H1.
Đổi schema ở đây ⇒ frontend sinh lại kiểu (npm run gen:api) sẽ báo lỗi ngay khi build.

Quy ước:
- Cạnh nối theo `key` của nút (ổn định giữa các phiên bản, mục 5.2.5), không theo `id`.
- `TreeVersion` tự kiểm: key nút không trùng, cạnh trỏ tới nút có thật, không cạnh tự trỏ (BR-01).
  Kiểm chu trình nằm ở `app/algorithms/dag.py` (cần trả đường đi, FR-SK-07).
"""

from datetime import datetime
from uuid import UUID

from pydantic import Field, model_validator

from app.models.enums import BloomLevel, EdgeSource, TreeStatus
from app.models.schemas.common import ApiModel


class KeyPointSchema(ApiModel):
    id: str  # "KP1"…
    content: str
    is_required: bool = True


class MisconceptionSchema(ApiModel):
    id: str  # "MC1"…
    content: str
    probe_question: str | None = None
    is_critical: bool = False


class ChallengeScenarioSchema(ApiModel):
    id: str  # "SC1"…
    scenario: str
    bloom_level: BloomLevel
    expected_points: str | None = None  # ý SV cần nêu khi trả lời tình huống (cột challenge_scenarios)


class Rubric(ApiModel):
    """Ý chính, quan niệm sai, tình huống phản biện, mức Bloom, trang (FR-SK-05, Bảng 6.1)."""

    key_points: list[KeyPointSchema]
    optional_points: list[str] = []
    misconceptions: list[MisconceptionSchema] = []
    scenarios: list[ChallengeScenarioSchema] = []
    target_bloom: BloomLevel = BloomLevel.UNDERSTAND
    pass_threshold: int = Field(70, ge=0, le=100)
    min_challenges: int = 3
    min_passed_challenges: int = 2  # k trong BR-03
    source_pages: list[int] = []
    approved: bool = False


class Node(ApiModel):
    id: UUID | None = None
    key: str = Field(pattern=r"^[a-z0-9_]+$")
    code: str | None = None  # nhãn hiển thị "N5"
    title: str = Field(max_length=200)
    description: str | None = None
    chapter_ref: str | None = None
    source_page_start: int | None = None  # trang đầu / cuối trong giáo trình nơi khái niệm được trích (C1-20)
    source_page_end: int | None = None
    aliases: list[
        str
    ] = []  # key cũ của các nút đã gộp vào nút này: MasteryService ghép ô thành thạo theo key hoặc alias
    bloom_level: BloomLevel = BloomLevel.UNDERSTAND
    position_x: float | None = None
    position_y: float | None = None
    rubric: Rubric | None = None


class NodePatch(ApiModel):
    """PATCH /nodes/{id} (C2-09): chỉ gửi trường cần đổi – kéo thả chỉ cần positionX / positionY. Không đổi được key."""

    code: str | None = None
    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    chapter_ref: str | None = None
    bloom_level: BloomLevel | None = None
    position_x: float | None = None
    position_y: float | None = None


class Edge(ApiModel):
    """X → Y: phải hiểu X (from) trước khi học Y (to)."""

    id: UUID | None = None
    from_key: str
    to_key: str
    source: EdgeSource = EdgeSource.AI
    confidence: float | None = Field(None, ge=0, le=1)


class TreeVersion(ApiModel):
    id: UUID | None = None
    class_id: UUID | None = None
    version_no: int = 1
    status: TreeStatus = TreeStatus.DRAFT
    change_note: str | None = None
    published_at: datetime | None = None
    nodes: list[Node]
    edges: list[Edge]

    @model_validator(mode="after")
    def _check_keys(self) -> "TreeVersion":
        seen: set[str] = set()
        for n in self.nodes:
            if n.key in seen:
                raise ValueError(f"key nút bị trùng: {n.key}")
            seen.add(n.key)
        for e in self.edges:
            if e.from_key == e.to_key:
                raise ValueError(f"cạnh tự trỏ: {e.from_key}")
            for k in (e.from_key, e.to_key):
                if k not in seen:
                    raise ValueError(f"cạnh {e.from_key}→{e.to_key}: key {k} không có trong danh sách nút")
        return self


class CycleError(ApiModel):
    """Trả kèm 409 CYCLE_DETECTED (FR-SK-07, TC03): đường đi của chu trình theo key."""

    path: list[str]


class EdgeRef(ApiModel):
    from_key: str
    to_key: str


class TreeDiff(ApiModel):
    """So sánh hai phiên bản cây (FR-SK-10) theo key nút – key ổn định giữa các phiên bản."""

    from_version_no: int
    to_version_no: int
    nodes_added: list[str]
    nodes_removed: list[str]
    nodes_changed: list[str]  # cùng key nhưng khác tiêu đề, mô tả, Bloom, vị trí hoặc rubric
    edges_added: list[EdgeRef]
    edges_removed: list[EdgeRef]


class PublishBody(ApiModel):
    """Thân tùy chọn của POST /tree-versions/{id}/publish: ghi chú thay đổi hiện ở lịch sử phiên bản (FR-SK-10)."""

    change_note: str | None = Field(None, max_length=500)


class ApproveRubricsBody(ApiModel):
    node_ids: list[UUID] = Field(max_length=1000)


class RejectedRubric(ApiModel):
    node_id: UUID
    reason: str


class ApproveRubricsResult(ApiModel):
    """Duyệt hàng loạt (FR-SK-08): chỉ rubric hợp lệ được duyệt, phần còn lại kèm lý do để GV sửa."""

    approved: list[UUID]
    rejected: list[RejectedRubric]


class PublishCheck(ApiModel):
    """GET /classes/{id}/tree/publish-check: xem trước phát hành (BR-05, BR-14) mà không đổi gì."""

    ok: bool
    version_id: UUID
    version_no: int
    errors: list[dict] = []  # cùng khuôn `details.errors` của 422 PUBLISH_CHECK_FAILED
    unapproved_count: int
    affected_students: int  # SV đã tham gia lớp: trạng thái thành thạo được khởi tạo / di chuyển khi phát hành
    older_than_published: bool  # bản nháp cũ hơn bản đang phát hành ⇒ phát hành sẽ thay bản mới hơn


class TreeVersionSummary(ApiModel):
    """Một dòng lịch sử phiên bản (FR-SK-10): không kèm cả cây như TreeVersion."""

    id: UUID
    version_no: int
    status: TreeStatus
    change_note: str | None = None
    created_at: datetime | None = None
    published_at: datetime | None = None
    node_count: int
    edge_count: int


class NodePosition(ApiModel):
    node_id: UUID
    x: float
    y: float


class PositionsBody(ApiModel):
    positions: list[NodePosition] = Field(max_length=1000)
