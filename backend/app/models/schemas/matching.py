"""Hợp đồng API ghép cặp bạn cùng tiến – MX4 (FR-PM-01…07). Chủ: Long (C2-14). JSON camelCase.

Mã lỗi:
- 404 MATCH_NOT_FOUND · 403 NOT_MATCH_MEMBER (không phải người trong cặp)
- 409 MATCH_INVALID_STATE details {status} – thao tác không hợp lệ ở trạng thái hiện tại (Hình 4.30)
- 409 MATCH_EXPIRED details {status} – quá hạn (48 giờ chờ chấp nhận / 7 ngày chưa học cùng)
- 409 NOT_ENOUGH_PARTICIPANTS details {participantCount} – < 2 SV bật ghép cặp và chưa có cặp hoạt động
- 404 ENROLLMENT_NOT_FOUND · 403 FORBIDDEN (ghi danh của SV khác) · 403 NOT_CLASS_OWNER · 403 NOT_ENROLLED
- 404 TREE_NOT_PUBLISHED (lớp chưa phát hành cây)
- 404 NODE_NOT_IN_TREE (nút không thuộc cây đang phát hành) – C2-15
- 422 DEADLINE_IN_PAST (hạn kiểm tra bài cũ phải ở tương lai) – C2-15
- PATCH /matches/{id} (C2-15): 409 MATCH_INVALID_STATE (cặp đã kết thúc) · 422 REPLACE_NOT_IN_MATCH ·
  404 STUDENT_NOT_IN_CLASS · 409 STUDENT_NOT_OPTED_IN · 409 STUDENT_BUSY (đang trong cặp hoạt động khác) ·
  422 NO_COMPLEMENTARY_NODES (hai SV không có gì để dạy nhau)
"""

from datetime import datetime
from uuid import UUID

from pydantic import model_validator

from app.models.enums import MatchStatus
from app.models.schemas.common import ApiModel


class RoundRequest(ApiModel):
    priority_node_id: UUID | None = None  # "Ghép cặp ưu tiên N5" (FR-PM-04, C2-15): ưu tiên cặp có người dạy nút này


class MatchAdjust(ApiModel):
    """GV điều chỉnh cặp thủ công (FR-PM-08, C2-15): hủy cặp (`cancel`) hoặc thay một SV bằng SV khác trong lớp.
    Thay SV ⇒ tính lại nút dạy / học, cặp quay về PROPOSED để hai bên chấp nhận lại."""

    cancel: bool = False
    replace_student_id: UUID | None = None
    with_student_id: UUID | None = None

    @model_validator(mode="after")
    def _one_action(self) -> "MatchAdjust":
        swap = self.replace_student_id is not None or self.with_student_id is not None
        if self.cancel == swap:
            raise ValueError("chọn đúng một: cancel=true hoặc (replaceStudentId + withStudentId)")
        if swap and (self.replace_student_id is None or self.with_student_id is None):
            raise ValueError("thay SV cần cả replaceStudentId và withStudentId")
        return self


class MatchingStats(ApiModel):
    """Hiệu quả ghép cặp của lớp (mục 6.6.6, FR-PM-08)."""

    total_matches: int
    accepted: int  # cả hai đã chấp nhận
    declined: int
    expired: int
    studied: int  # cả hai bấm "Đã học cùng"
    items_total: int  # mục dạy–học của các cặp đã học cùng
    items_verified: int  # trong đó người học đã Đạt khi xác nhận lại
    accept_rate: float  # accepted / total_matches
    studied_rate: float  # studied / accepted
    verified_rate: float  # items_verified / items_total


class MatchItemOut(ApiModel):
    """Một chiều dạy → học của một nút. SV học dùng `id` làm `peerMatchItemId` khi mở phiên xác nhận lại."""

    id: UUID
    teacher_id: UUID
    learner_id: UUID
    node_id: UUID
    node_key: str
    verified: bool
    verified_at: datetime | None = None


class MatchOut(ApiModel):
    """Một gợi ý ghép cặp nhìn từ phía người xem. SV: "tôi" là SV đang đăng nhập. GV: góc nhìn của SV A."""

    id: UUID
    partner_id: UUID
    partner_name: str
    partner_email: str | None = None  # chỉ chia sẻ khi cả hai đã chấp nhận (UC22 bước 2)
    i_teach: list[str]  # key nút
    i_learn: list[str]
    status: MatchStatus
    weight: float
    expires_at: datetime  # hạn của trạng thái hiện tại (BR-09)
    one_way: bool = False  # ghép một chiều cho SV lẻ (A là mentor)
    accepted_by_me: bool = False
    studied_by_me: bool = False
    student_a_id: UUID
    student_a_name: str
    student_b_id: UUID
    student_b_name: str
    items: list[MatchItemOut] = []
    created_at: datetime


class RoundOut(ApiModel):
    id: UUID
    trigger_type: str  # MANUAL / SCHEDULED / LIVE (ghép theo sự kiện trong hạn kiểm tra, C2-15)
    participant_count: int
    total_weight: float
    matches: list[MatchOut]
    waiting_student_ids: list[UUID] = []  # SV chưa ghép được – chờ vòng sau
    created_at: datetime


class OptIn(ApiModel):
    peer_opt_in: bool


class ReviewWindowRequest(ApiModel):
    deadline_at: datetime  # phải ở tương lai; đặt lại cho cùng nút thì dời hạn


class ReviewWindowOut(ApiModel):
    """Hạn kiểm tra bài cũ của một nút (C2-15). Trong hạn, ghép cặp chạy theo sự kiện: người Đạt dạy tối đa 3 người
    chưa Đạt; không đạt ⇒ ghép ngay với người dạy còn chỗ, chưa có ⇒ chờ. Hết hạn thì dừng ghép tự động."""

    node_id: UUID | None  # nút ở bản đang phát hành (None nếu key không còn trong cây)
    node_key: str
    deadline_at: datetime
    open: bool
    teacher_count: int  # SV bật ghép cặp đã Đạt nút (người dạy tiềm năng)
    matched_count: int  # SV chưa Đạt đang có cặp ở nút này
    waiting_student_ids: list[UUID] = []  # SV chưa Đạt chưa có người dạy – GV giảng trực tiếp hoặc ghép tay
    message: str | None = None
