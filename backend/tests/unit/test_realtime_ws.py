"""C2-13 – cổng WebSocket /api/v1/ws (Bảng 5.11) không cần CSDL: xác thực token theo từng lệnh subscribe,
quyền kênh, giao tin {channel, event, payload} như frontend/src/lib/ws.ts. Kiểm quyền lớp trên CSDL thật:
test_heatmap_api_db.py.
"""

import json
import os
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api import realtime
from app.api.deps import _dev_user
from app.core.errors import AppError
from app.core.security import create_access_token
from app.main import app
from app.models.enums import HeatColor, MasteryState, Role
from app.models.schemas.mastery import HeatmapCell, HeatmapNode
from app.realtime import gateway
from app.services.auth import InMemoryRevocations

LECTURER = _dev_user("dev-lecturer")
CLASS_ID = uuid4()
CHANNEL = gateway.channel_heatmap(CLASS_ID)
JOB_ID = str(uuid4())
SESSION_ID = uuid4()


@pytest.fixture
def ws_client():
    """Chủ lớp = GV dev; lớp khác ⇒ 403 NOT_CLASS_OWNER (thay cho truy vấn class_sections)."""

    def owner_check(class_id: UUID, user) -> None:
        if class_id != CLASS_ID:
            raise AppError(403, "NOT_CLASS_OWNER", "Chỉ GV phụ trách lớp được thao tác")

    def job_check(job_id: str, user) -> None:
        if job_id != JOB_ID:
            raise AppError(404, "JOB_NOT_FOUND", "Không tìm thấy job")

    def session_check(session_id: UUID, user) -> None:
        if session_id != SESSION_ID:
            raise AppError(403, "FORBIDDEN", "Đây không phải phiên của bạn")

    app.dependency_overrides[realtime.get_class_owner_check] = lambda: owner_check
    app.dependency_overrides[realtime.get_job_owner_check] = lambda: job_check
    app.dependency_overrides[realtime.get_session_owner_check] = lambda: session_check
    yield TestClient(app)
    app.dependency_overrides.pop(realtime.get_class_owner_check, None)
    app.dependency_overrides.pop(realtime.get_job_owner_check, None)
    app.dependency_overrides.pop(realtime.get_session_owner_check, None)


def sub(ws, channel=CHANNEL, token="dev-lecturer", action="subscribe"):
    ws.send_json({"action": action, "channel": channel, "token": token})
    return ws.receive_json()


def test_subscribe_dung_gv_chu_lop_nhan_ack_va_su_kien(ws_client):
    with ws_client.websocket_connect("/api/v1/ws") as ws:
        assert sub(ws) == {"channel": CHANNEL, "event": "subscribed", "payload": {}}
        node = HeatmapNode(node_id=uuid4(), node_key="n5_con_tro", color=HeatColor.RED, pass_rate=0.2, attempted_rate=1)
        gateway.broadcast(CHANNEL, gateway.EVENT_HEATMAP_NODE, node)
        msg = ws.receive_json()
        assert msg["channel"] == CHANNEL and msg["event"] == "heatmap.node"
        assert msg["payload"]["nodeKey"] == "n5_con_tro" and msg["payload"]["color"] == "RED"  # camelCase


def test_jwt_that_cung_duoc(ws_client):
    token = create_access_token(LECTURER.id, Role.LECTURER, "GV")
    with ws_client.websocket_connect("/api/v1/ws") as ws:
        assert sub(ws, token=token)["event"] == "subscribed"


@pytest.mark.parametrize("token", [["dev-lecturer"], {"accessToken": "dev-lecturer"}])
def test_token_json_khong_phai_chuoi_tra_loi_co_cau_truc(token):
    """JSON subscribe có thể chứa mảng/object: phải trả INVALID_TOKEN thay vì làm văng endpoint."""
    with pytest.raises(AppError) as exc:
        realtime.user_from_token(token, InMemoryRevocations())
    assert exc.value.status == 401
    assert exc.value.code == "INVALID_TOKEN"


@pytest.mark.parametrize(
    ("token", "code"),
    [(None, "UNAUTHORIZED"), ("", "UNAUTHORIZED"), ("rac", "INVALID_TOKEN"), ("dev-student", "FORBIDDEN")],
)
def test_token_sai_hoac_sai_vai_bi_tu_choi(ws_client, token, code):
    with ws_client.websocket_connect("/api/v1/ws") as ws:
        msg = sub(ws, token=token)
        assert msg["channel"] == CHANNEL and msg["event"] == "error"
        assert msg["payload"]["code"] == code
        # bị từ chối thì không nhận tin của kênh
        gateway.broadcast(CHANNEL, gateway.EVENT_HEATMAP_CELL, {"x": 1})
        ws.send_json({"action": "ping"})
        assert ws.receive_json()["event"] == "pong"


def test_gv_khong_phu_trach_lop_bi_403(ws_client):
    other = gateway.channel_heatmap(uuid4())
    with ws_client.websocket_connect("/api/v1/ws") as ws:
        msg = sub(ws, channel=other)
        assert msg["event"] == "error" and msg["payload"]["code"] == "NOT_CLASS_OWNER"
        assert gateway.hub.listeners(other) == 0


@pytest.mark.parametrize(
    ("channel", "code"),
    [
        ("class:khong-phai-uuid:heatmap", "UNKNOWN_CHANNEL"),
        ("lung:tung", "UNKNOWN_CHANNEL"),
        (None, "UNKNOWN_CHANNEL"),
        (f"user:{uuid4()}", "FORBIDDEN"),  # kênh của người khác
        (f"job:{uuid4()}", "JOB_NOT_FOUND"),  # job không phải của GV này / không tồn tại
        ("job:khong-phai-uuid", "UNKNOWN_CHANNEL"),
        (f"session:{uuid4()}", "FORBIDDEN"),  # không phải phiên của SV này
        ("session:khong-phai-uuid", "UNKNOWN_CHANNEL"),
    ],
)
def test_kenh_khong_hop_le(ws_client, channel, code):
    with ws_client.websocket_connect("/api/v1/ws") as ws:
        assert sub(ws, channel=channel)["payload"]["code"] == code


def test_kenh_job_gv_da_tai_nhan_tien_do(ws_client):
    """C1-09: GV vừa tải giáo trình nghe job:{jobId} và nhận job.progress do worker phát."""
    channel = gateway.channel_job(JOB_ID)
    with ws_client.websocket_connect("/api/v1/ws") as ws:
        assert sub(ws, channel=channel)["event"] == "subscribed"
        gateway.broadcast(channel, "job.progress", {"percent": 40, "step": "OCR"})
        msg = ws.receive_json()
        assert msg == {"channel": channel, "event": "job.progress", "payload": {"percent": 40, "step": "OCR"}}


def test_kenh_job_sv_bi_chan_theo_vai(ws_client):
    with ws_client.websocket_connect("/api/v1/ws") as ws:
        msg = sub(ws, channel=gateway.channel_job(JOB_ID), token="dev-student")
        assert msg["payload"]["code"] == "FORBIDDEN"


def test_kenh_user_cua_chinh_minh(ws_client):
    channel = gateway.channel_user(LECTURER.id)
    with ws_client.websocket_connect("/api/v1/ws") as ws:
        assert sub(ws, channel=channel)["event"] == "subscribed"


def test_tin_hong_va_action_la(ws_client):
    with ws_client.websocket_connect("/api/v1/ws") as ws:
        ws.send_text("không phải json")
        assert ws.receive_json()["payload"]["code"] == "BAD_MESSAGE"
        ws.send_json({"action": "nhay"})
        assert ws.receive_json()["payload"]["code"] == "BAD_MESSAGE"


def test_unsubscribe_thi_het_nhan_tin(ws_client):
    with ws_client.websocket_connect("/api/v1/ws") as ws:
        sub(ws)
        assert sub(ws, action="unsubscribe") == {"channel": CHANNEL, "event": "unsubscribed", "payload": {}}
        gateway.broadcast(CHANNEL, gateway.EVENT_HEATMAP_CELL, {"x": 1})
        ws.send_json({"action": "ping"})
        assert ws.receive_json()["event"] == "pong"


def test_dong_ket_noi_thi_go_khoi_hub(ws_client):
    with ws_client.websocket_connect("/api/v1/ws") as ws:
        sub(ws)
        assert gateway.hub.listeners(CHANNEL) == 1
    # sau khi đóng, endpoint dọn hub (đợi bằng một kết nối mới để chắc vòng lặp đã xử lý xong)
    with ws_client.websocket_connect("/api/v1/ws") as ws:
        ws.send_json({"action": "ping"})
        ws.receive_json()
    assert gateway.hub.listeners(CHANNEL) == 0


def test_hai_gv_cung_kenh_deu_nhan(ws_client):
    with ws_client.websocket_connect("/api/v1/ws") as a, ws_client.websocket_connect("/api/v1/ws") as b:
        sub(a)
        sub(b)
        cell = HeatmapCell(
            student_id=uuid4(), student_name="Nguyễn Văn A", node_id=uuid4(), state=MasteryState.MASTERED
        )
        gateway.broadcast(CHANNEL, gateway.EVENT_HEATMAP_CELL, cell)
        for ws in (a, b):
            msg = ws.receive_json()
            assert msg["event"] == "heatmap.cell" and msg["payload"]["studentName"] == "Nguyễn Văn A"


# --- gateway / hub thuần ------------------------------------------------------------------------------


def test_encode_dung_dinh_dang_ws_ts():
    msg = json.loads(gateway.encode("class:x:heatmap", "heatmap.alert", {"message": "Nên giảng lại N5 Con trỏ"}))
    assert msg == {
        "channel": "class:x:heatmap",
        "event": "heatmap.alert",
        "payload": {"message": "Nên giảng lại N5 Con trỏ"},
    }


def test_relay_redis_giao_tin_cho_hub():
    """RedisRelay đọc pmessage "ws:<kênh>" và giao cho hub (client Redis giả, không cần máy chủ)."""
    import threading

    got: list[tuple[str, str]] = []
    done = threading.Event()

    class FakeHub:
        def deliver(self, channel, message):
            got.append((channel, message))
            done.set()
            return 1

    class FakePubSub:
        def __init__(self):
            self.sent = False

        def psubscribe(self, pattern):
            assert pattern == "ws:*"

        def get_message(self, timeout):
            if not self.sent:
                self.sent = True
                return {"type": "pmessage", "channel": b"ws:class:1:heatmap", "data": b'{"event":"heatmap.node"}'}
            done.wait(timeout)
            return None

        def close(self):
            pass

    class FakeRedis:
        def pubsub(self, ignore_subscribe_messages):
            return FakePubSub()

    relay = gateway.RedisRelay(client=FakeRedis(), target=FakeHub())
    relay.start()
    assert done.wait(5)
    relay.stop()
    assert got == [("class:1:heatmap", '{"event":"heatmap.node"}')]


@pytest.mark.skipif(not os.getenv("TEST_REDIS_URL"), reason="đặt TEST_REDIS_URL để chạy qua Redis thật")
def test_mt5_qua_redis_that_duoi_3_giay():
    """Worker publish "ws:<kênh>" → RedisRelay (tiến trình api) → hub ≤ 3 giây."""
    import threading
    import time

    import redis

    url = os.environ["TEST_REDIS_URL"]
    channel = gateway.channel_heatmap(uuid4())
    target = gateway.Hub()
    got = threading.Event()

    class Probe:
        def push(self, message):
            got.set()

    target.subscribe(channel, Probe())
    relay = gateway.RedisRelay(redis_url=url, target=target)
    relay.start()
    try:
        t0 = time.perf_counter()
        redis.Redis.from_url(url).publish(gateway.REDIS_PREFIX + channel, gateway.encode(channel, "heatmap.node", {}))
        assert got.wait(3.0)
        assert time.perf_counter() - t0 <= 3.0
    finally:
        relay.stop()


def test_kenh_phien_sv_chu_phien_nhan_cau_hoi_cua_tutee(ws_client):
    """C1-07: SV chủ phiên nghe session:{id} và nhận session.question do Orchestrator phát."""
    channel = gateway.channel_session(SESSION_ID)
    with ws_client.websocket_connect("/api/v1/ws") as ws:
        assert sub(ws, channel=channel, token="dev-student")["event"] == "subscribed"
        payload = {"text": "Con trỏ khác biến thường ở chỗ nào?", "audioUrl": None, "deadline": None}
        gateway.broadcast(channel, "session.question", payload)
        assert ws.receive_json() == {"channel": channel, "event": "session.question", "payload": payload}


def test_kenh_phien_gv_va_admin_khong_nghe_duoc(ws_client):
    channel = gateway.channel_session(SESSION_ID)
    with ws_client.websocket_connect("/api/v1/ws") as ws:
        assert sub(ws, channel=channel, token="dev-lecturer")["payload"]["code"] == "FORBIDDEN"
        assert sub(ws, channel=channel, token="dev-admin")["payload"]["code"] == "FORBIDDEN"
