"""Gửi email thông báo (FR-AD-08). Chủ: Long (C2-19). Chưa cấu hình SMTP_HOST thì chỉ ghi log (dev / demo)."""

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import get_settings
from app.workers.celery_app import celery

log = logging.getLogger(__name__)


@celery.task(
    name="app.workers.notifications.deliver_email",
    autoretry_for=(OSError, smtplib.SMTPException),
    retry_backoff=True,
    max_retries=3,
)
def deliver_email(to: str, subject: str, body: str) -> bool:
    s = get_settings()
    if not s.smtp_host:
        log.info("SMTP chưa cấu hình – bỏ qua email tới %s: %s", to.partition("@")[2], subject)
        return False
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s.smtp_from, to, subject
    msg.set_content(body)
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
        smtp.starttls()
        if s.smtp_user:
            smtp.login(s.smtp_user, s.smtp_password)
        smtp.send_message(msg)
    return True
