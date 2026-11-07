"""Cổng WebSocket (RealtimeGateway – Hình 5.11). Kênh theo Bảng 5.11:
  job:{jobId}          job.progress, tree.generated            (C2-08, C1-09) – chỉ GV phụ trách lớp của tài liệu
  class:{id}:heatmap   heatmap.cell, heatmap.node, heatmap.alert (C2-13) – chỉ GV phụ trách lớp
  user:{id}            notification                             (C2-19) – chỉ chính người đó
  session:{id}         session.question                         (C1-07) – chỉ SV chủ phiên

Client gửi (frontend/src/lib/ws.ts):
  {"action": "subscribe" | "unsubscribe", "channel": "class:<id>:heatmap", "token": "<jwt>"}  ·  {"action": "ping"}
Máy chủ trả {channel, event, payload}:
  subscribed / unsubscribed (payload {}), pong, error (payload {code, message, details} – như AppError),
  và các sự kiện của kênh do `app.realtime.gateway.broadcast` phát.
Token kiểm ở MỖI lệnh subscribe (ws.ts gửi kèm token mỗi lần, kể cả khi nối lại).
"""

import asyncio
import json
import logging
import re
from collections.abc import Callable
from contextlib import suppress
from uuid import UUID

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from app.api.deps import CurrentUser, get_revocations, user_from_token
from app.core.errors import AppError
from app.models.enums import Role
from app.realtime import gateway
from app.services.auth import Revocations

log = logging.getLogger(__name__)

router = APIRouter(tags=["realtime"])

ClassOwnerCheck = Callable[[UUID, CurrentUser], None]
JobOwnerCheck = Callable[[str, CurrentUser], None]
SessionOwnerCheck = Callable[[UUID, CurrentUser], None]

_HEATMAP = re.compile(r"^class:([0-9a-fA-F-]{36}):heatmap$")
_USER = re.compile(r"^user:([0-9a-fA-F-]{36})$")
_JOB = re.compile(r"^job:([0-9a-fA-F-]{36})$")
_SESSION = re.compile(r"^session:([0-9a-fA-F-]{36})$")


def _check_class_owner(class_id: UUID, user: CurrentUser) -> None:
    from app.db.session import SessionLocal
    from app.services.heatmap import HeatmapService

    with SessionLocal() as db:  # phiên ngắn cho mỗi lệnh subscribe – không giữ kết nối CSDL suốt WebSocket
        HeatmapService(db).require_owner(class_id, user)


def get_class_owner_check() -> ClassOwnerCheck:
    """Dependency (test ghi đè): kiểm GV phụ trách lớp – 404 CLASS_NOT_FOUND / 403 NOT_CLASS_OWNER."""
    return _check_class_owner


def _check_job_owner(job_id: str, user: CurrentUser) -> None:
    from app.db.session import SessionLocal
    from app.services.syllabus import require_job_owner

    with SessionLocal() as db:
        require_job_owner(db, job_id, user)


def get_job_owner_check() -> JobOwnerCheck:
    """Dependency (test ghi đè): kiểm GV đã tải tài liệu của job – 404 JOB_NOT_FOUND / 403 NOT_CLASS_OWNER."""
    return _check_job_owner


def _check_session_owner(session_id: UUID, user: CurrentUser) -> None:
    from app.db.session import SessionLocal
    from app.models.session import TeachingSession

    with SessionLocal() as db:
        s = db.get(TeachingSession, session_id)
        if s is None:
            raise AppError(404, "SESSION_NOT_FOUND", "Không tìm thấy phiên", {"sessionId": str(session_id)})
        if s.student_id != user.id:
            raise AppError(403, "FORBIDDEN", "Đây không phải phiên của bạn")


def get_session_owner_check() -> SessionOwnerCheck:
    """Dependency (test ghi đè): kiểm SV là chủ phiên – 404 SESSION_NOT_FOUND / 403 FORBIDDEN."""
    return _check_session_owner


def _uuid(raw: str) -> UUID:
    try:
        return UUID(raw)
    except ValueError:
        raise AppError(400, "UNKNOWN_CHANNEL", "Kênh không hợp lệ") from None


def authorize(
    user: CurrentUser,
    channel: object,
    owner_check: ClassOwnerCheck,
    job_check: JobOwnerCheck,
    session_check: SessionOwnerCheck = _check_session_owner,
) -> None:
    """Ném AppError nếu `user` không được nghe `channel` (chặn theo vai trước khi chạm CSDL)."""
    if not isinstance(channel, str):
        raise AppError(400, "UNKNOWN_CHANNEL", "Thiếu kênh")
    if m := _HEATMAP.match(channel):
        class_id = _uuid(m.group(1))
        if user.role != Role.LECTURER:
            raise AppError(403, "FORBIDDEN", "Vai trò không được phép")
        owner_check(class_id, user)
        return
    if m := _JOB.match(channel):
        job_id = str(_uuid(m.group(1)))
        if user.role != Role.LECTURER:
            raise AppError(403, "FORBIDDEN", "Vai trò không được phép")
        job_check(job_id, user)
        return
    if m := _USER.match(channel):
        if _uuid(m.group(1)) != user.id:
            raise AppError(403, "FORBIDDEN", "Chỉ nghe được kênh của chính mình")
        return
    if m := _SESSION.match(channel):
        session_id = _uuid(m.group(1))
        if user.role != Role.STUDENT:
            raise AppError(403, "FORBIDDEN", "Vai trò không được phép")
        session_check(session_id, user)  # session.question của Tutee: chỉ SV chủ phiên nghe
        return
    raise AppError(400, "UNKNOWN_CHANNEL", "Kênh không hợp lệ", {"channel": channel})


def _msg(channel: object, event: str, payload: dict | None = None) -> str:
    return json.dumps(
        {"channel": channel if isinstance(channel, str) else None, "event": event, "payload": payload or {}},
        ensure_ascii=False,
    )


def _error(channel: object, exc: AppError) -> str:
    return _msg(channel, "error", {"code": exc.code, "message": exc.message, "details": exc.details})


@router.websocket("/ws")
async def ws_endpoint(
    ws: WebSocket,
    revocations: Revocations = Depends(get_revocations),
    owner_check: ClassOwnerCheck = Depends(get_class_owner_check),
    job_check: JobOwnerCheck = Depends(get_job_owner_check),
    session_check: SessionOwnerCheck = Depends(get_session_owner_check),
) -> None:
    await ws.accept()
    gateway.ensure_relay()
    conn = gateway.Connection(loop=asyncio.get_running_loop())
    subscribed: set[str] = set()

    async def pump() -> None:
        while True:
            await ws.send_text(await conn.queue.get())

    sender = asyncio.create_task(pump())

    async def handle(raw: str) -> None:
        try:
            msg = json.loads(raw)
        except ValueError:
            msg = None
        if not isinstance(msg, dict):
            conn.push(_error(None, AppError(400, "BAD_MESSAGE", "Tin nhắn phải là JSON object")))
            return
        action, channel = msg.get("action"), msg.get("channel")
        if action == "ping":
            conn.push(_msg(None, "pong"))
            return
        if action == "unsubscribe":
            if isinstance(channel, str):
                gateway.hub.unsubscribe(channel, conn)
                subscribed.discard(channel)
            conn.push(_msg(channel, "unsubscribed"))
            return
        if action != "subscribe":
            conn.push(_error(channel, AppError(400, "BAD_MESSAGE", "action phải là subscribe | unsubscribe | ping")))
            return
        try:
            user = user_from_token(msg.get("token"), revocations)
            await run_in_threadpool(authorize, user, channel, owner_check, job_check, session_check)
        except AppError as exc:
            conn.push(_error(channel, exc))
            return
        gateway.hub.subscribe(channel, conn)
        subscribed.add(channel)
        conn.push(_msg(channel, "subscribed"))

    try:
        while True:
            await handle(await ws.receive_text())
    except WebSocketDisconnect:
        pass
    finally:
        gateway.hub.drop(conn)
        sender.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await sender
