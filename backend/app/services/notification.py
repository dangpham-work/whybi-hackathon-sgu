"""NotificationService – thông báo trong ứng dụng (kênh `user:{id}`) và email (FR-AD-08). Chủ: Long (C2-19).

`notify` chỉ ghi dòng `notifications` (flush) và xếp việc giao vào `session.info`; việc giao thật – đẩy WebSocket
và gửi email – chạy SAU khi giao dịch của bên gọi commit (hook `after_commit` bên dưới). Rollback thì bỏ hết,
nên người dùng không bao giờ nhận thông báo về việc chưa xảy ra. Đẩy WebSocket / email lỗi chỉ ghi log: thông báo
đã lưu, người dùng vẫn thấy khi mở ứng dụng.
"""

import logging
from collections.abc import Callable
from uuid import UUID

from sqlalchemy import event, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.models.schemas.notification import NotificationOut
from app.models.users import Notification, User
from app.realtime.gateway import broadcast, channel_user

log = logging.getLogger(__name__)

PENDING = "pending_notifications"  # khóa trong Session.info

EVENT_NOTIFICATION = "notification"


def send_email(to: str, subject: str, body: str) -> None:
    """Đưa email vào hàng đợi Celery (không chặn request). Môi trường test chỉ ghi log."""
    if get_settings().app_env == "test":
        log.info("[test] email tới %s: %s", to, subject)
        return
    from app.workers.notifications import deliver_email

    deliver_email.delay(to, subject, body)


EmailSender = Callable[[str, str, str], None]
email_sender: EmailSender = send_email  # test thay bằng hàm ghi nhận


def _deliver(item: dict) -> None:
    try:
        broadcast(channel_user(item["user_id"]), EVENT_NOTIFICATION, item["payload"])
    except Exception:  # noqa: BLE001 – Redis rớt: thông báo đã lưu, GV / SV thấy khi tải lại
        log.exception("không đẩy được notification tới user %s", item["user_id"])
    if item["email"]:
        try:
            email_sender(item["email"], item["subject"], item["body"])
        except Exception:  # noqa: BLE001
            log.exception("không xếp được email tới user %s", item["user_id"])


@event.listens_for(Session, "after_commit")
def _after_commit(session: Session) -> None:
    for item in session.info.pop(PENDING, []):
        _deliver(item)


@event.listens_for(Session, "after_rollback")
def _after_rollback(session: Session) -> None:
    session.info.pop(PENDING, None)


class NotificationService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def notify(
        self,
        user_id: UUID,
        type: str,
        title: str,
        content: str | None = None,
        link: str | None = None,
        *,
        email: bool = False,
    ) -> NotificationOut:
        """Tạo thông báo cho một người dùng. Bên gọi commit thì mới giao (WebSocket, và email nếu `email=True`)."""
        n = Notification(user_id=user_id, type=type, title=title, content=content, link=link, is_read=False)
        self.db.add(n)
        self.db.flush()
        out = self._out(n)
        address = self.db.scalar(select(User.email).where(User.id == user_id)) if email else None
        self.db.info.setdefault(PENDING, []).append(
            {
                "user_id": user_id,
                "payload": out,
                "email": address,
                "subject": f"[Whybi AI] {title}",
                "body": "\n\n".join(x for x in (content, link) if x),
            }
        )
        return out

    @staticmethod
    def _out(n: Notification) -> NotificationOut:
        return NotificationOut(
            id=n.id,
            type=n.type,
            title=n.title,
            content=n.content,
            link=n.link,
            is_read=n.is_read,
            created_at=n.created_at,
        )

    # ------------------------------------------------------------------ đọc, đánh dấu đã đọc

    def list(self, user_id: UUID, unread_only: bool = False, limit: int = 50) -> list[NotificationOut]:
        q = select(Notification).where(Notification.user_id == user_id)
        if unread_only:
            q = q.where(Notification.is_read.is_(False))
        q = q.order_by(Notification.created_at.desc(), Notification.id).limit(limit)
        return [self._out(n) for n in self.db.scalars(q)]

    def mark_read(self, user_id: UUID, notification_id: UUID) -> NotificationOut:
        """Thông báo của người khác hoặc không có ⇒ 404 (không lộ sự tồn tại)."""
        n = self.db.scalar(
            select(Notification).where(Notification.id == notification_id, Notification.user_id == user_id)
        )
        if n is None:
            raise AppError(404, "NOTIFICATION_NOT_FOUND", "Không tìm thấy thông báo")
        n.is_read = True
        self.db.commit()
        return self._out(n)

    def mark_all_read(self, user_id: UUID) -> int:
        res = self.db.execute(
            update(Notification)
            .where(Notification.user_id == user_id, Notification.is_read.is_(False))
            .values(is_read=True)
        )
        self.db.commit()
        return res.rowcount


# ------------------------------------------------------------------ thông báo của MX4 (ghép cặp)

PEERS_LINK = "/sv/classes/{class_id}/peers"  # màn SV-07 Bạn cùng tiến


def notify_match_proposed(db: Session, class_id: UUID, a: UUID, b: UUID) -> None:
    """Hai SV vừa được gợi ý ghép cặp (UC21): thông báo trong ứng dụng + email. Gọi trước commit của bên tạo cặp."""
    from app.services.auth import student_identities

    names = student_identities(db, [a, b])
    svc = NotificationService(db)
    for me, other in ((a, b), (b, a)):
        svc.notify(
            me,
            "MATCH_PROPOSED",
            "Có gợi ý bạn cùng tiến mới",
            f"Hệ thống gợi ý bạn học cùng {names.get(other, ('một bạn trong lớp', ''))[0]} để bổ trợ cho nhau. "
            "Hãy chấp nhận hoặc từ chối trong 48 giờ.",
            PEERS_LINK.format(class_id=class_id),
            email=True,
        )


def notify_match_accepted(db: Session, class_id: UUID, a: UUID, b: UUID) -> None:
    """Cả hai đã chấp nhận (UC22): gửi thông tin liên hệ của nhau (BR-07: chỉ chia sẻ khi cả hai đồng ý)."""
    from app.services.auth import student_identities

    names = student_identities(db, [a, b])
    emails = dict(db.execute(select(User.id, User.email).where(User.id.in_([a, b]))).all())
    svc = NotificationService(db)
    for me, other in ((a, b), (b, a)):
        svc.notify(
            me,
            "MATCH_ACCEPTED",
            "Cặp bạn cùng tiến đã được xác nhận",
            f"Bạn và {names.get(other, ('bạn học', ''))[0]} cùng chấp nhận. Liên hệ: {emails.get(other, '')}. "
            "Hãy học cùng nhau trong 7 ngày rồi bấm 'đã học'.",
            PEERS_LINK.format(class_id=class_id),
            email=True,
        )
