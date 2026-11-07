"""Hợp đồng API ghép cặp bạn cùng tiến – MX4 (FR-PM-01…07). Chủ: Long (C2-14). JSON camelCase.

Mã lỗi:
- 404 MATCH_NOT_FOUND · 403 NOT_MATCH_MEMBER (không phải người trong cặp)
- 409 MATCH_INVALID_STATE details {status} – thao tác không hợp lệ ở trạng thái hiện tại (Hình 4.30)
- 409 MATCH_EXPIRED details {status} – quá hạn (48 giờ chờ chấp nhận / 7 ngày chưa học cùng)
- 409 NOT_ENOUGH_PARTICIPANTS details {participantCount} – < 2 SV bật ghép cặp và chưa có cặp hoạt động
- 404 ENROLLMENT_NOT_FOUND · 403 FORBIDDEN (ghi danh của SV khác) · 403 NOT_CLASS_OWNER · 403 NOT_ENROLLED
- 404 TREE_NOT_PUBLISHED (lớp chưa phát hành cây)
"""

from datetime import datetime
from uuid import UUID

from app.models.enums import MatchStatus
from app.models.schemas.common import ApiModel


class RoundRequest(ApiModel):
    priority_node_id: UUID | None = None  # "Ghép cặp ưu tiên N5" (FR-PM-04, C2-15 – hiện trả 501)


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
    trigger_type: str  # MANUAL / SCHEDULED
    participant_count: int
    total_weight: float
    matches: list[MatchOut]
    waiting_student_ids: list[UUID] = []  # SV chưa ghép được – chờ vòng sau
    created_at: datetime


class OptIn(ApiModel):
    peer_opt_in: bool
