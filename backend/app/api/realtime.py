"""Cổng WebSocket (RealtimeGateway – Hình 5.11). Kênh theo Bảng 5.11:
  job:{jobId}          job.progress, tree.generated            (C2-08, C1-09)
  class:{id}:heatmap   heatmap.cell, heatmap.node, heatmap.alert (C2-13)
  user:{id}            notification                             (C2-19)
  session:{id}         session.question                         (C1-07)

Client gửi: {"action": "subscribe", "channel": "class:<id>:heatmap", "token": "<jwt>"}.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["realtime"])


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    try:
        while True:
            msg = await ws.receive_json()
            # TODO(C2-13): xác thực token, kiểm quyền kênh, đăng ký Redis Pub/Sub và đẩy sự kiện
            await ws.send_json({"event": "error", "payload": {"code": "NOT_IMPLEMENTED", "card": "C2-13", "echo": msg}})
    except WebSocketDisconnect:
        return
