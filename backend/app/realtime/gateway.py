"""RealtimeGateway – phát payload ra kênh WebSocket (Bảng 5.11). Chủ: Long (C2-13)."""

from typing import Any


def channel_heatmap(class_id: str) -> str:
    return f"class:{class_id}:heatmap"


def channel_job(job_id: str) -> str:
    return f"job:{job_id}"


def channel_user(user_id: str) -> str:
    return f"user:{user_id}"


def channel_session(session_id: str) -> str:
    return f"session:{session_id}"


def broadcast(channel: str, event: str, payload: dict[str, Any]) -> None:
    raise NotImplementedError("C2-13")
