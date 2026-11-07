"""Thông báo trong ứng dụng (FR-AD-08, Bảng 5.11 kênh `user:{id}`, sự kiện `notification`). Chủ: Long (C2-19)."""

from datetime import datetime
from uuid import UUID

from app.models.schemas.common import ApiModel


class NotificationOut(ApiModel):
    """Cùng dạng cho `GET /notifications` và payload `notification` trên kênh WebSocket."""

    id: UUID
    type: str  # vd. MATCH_PROPOSED, MATCH_ACCEPTED
    title: str
    content: str | None = None
    link: str | None = None  # đường dẫn trong ứng dụng, vd. /sv/classes/{id}/peers
    is_read: bool = False
    created_at: datetime
