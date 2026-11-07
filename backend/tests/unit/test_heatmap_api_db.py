"""C2-13 – Xong khi: GV thấy ô đổi màu trong ≤ 3 giây (MT5). CSDL thật (TEST_DATABASE_URL).

- GET /classes/{id}/heatmap: cây + màu theo key + lưới SV × nút có tên, MSSV; cảnh báo "Nên giảng lại N5 Con trỏ".
- GET /classes/{id}/nodes/{n}/detail: SV theo trạng thái (có tên), nút gốc.
- WebSocket class:{id}:heatmap: chỉ GV phụ trách lớp; luồng thật mastery.changed → tính lại → heatmap.node / cell
  / alert tới trình duyệt ≤ 3 giây (hàng đợi chạy đồng bộ trong test, gateway giao trong tiến trình).
"""

import time
from uuid import UUID, uuid4

import pytest

from app.api import realtime
from app.core.security import create_access_token
from app.main import app
from app.models.enums import Role
from app.realtime import gateway
from app.services import heatmap
from app.services.heatmap import HeatmapService
from tests.unit import test_rootcause_db as _c212
from tests.unit.test_heatmap_db import hoc
from tests.unit.test_tree_edit_db import DB_URL

world = _c212.world
lop30 = _c212.lop30
committed_world = _c212.committed_world
vi_du_6_9 = _c212.vi_du_6_9
N1, N5, N6 = _c212.N1, _c212.N5, _c212.N6

pytestmark = pytest.mark.skipif(not DB_URL, reason="đặt TEST_DATABASE_URL để chạy trên Postgres thật")

MT5_SECONDS = 3.0


def url(w, suffix=""):
    return f"/api/v1/classes/{w.class_id}{suffix}"


# --- GET /classes/{id}/heatmap -----------------------------------------------------------------------


def test_anh_chup_co_cay_luoi_ten_va_canh_bao(vi_du_6_9):
    w, ids, truot_n6 = vi_du_6_9
    r = w.api.get(url(w, "/heatmap"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["classId"] == str(w.class_id) and body["enrolledCount"] == 30
    assert len(body["tree"]["nodes"]) == 11  # truyền thẳng cho SkillTree
    nodes = {n["nodeKey"]: n for n in body["nodes"]}
    assert nodes[N6]["color"] == "RED" and nodes[N6]["label"].startswith("✗ Điểm nghẽn")
    assert nodes[N6]["rootCauseNodeKey"] == N5 and nodes[N5]["isRootCause"] is True
    assert nodes[N6]["attemptedCount"] == 12 and nodes[N6]["passedCount"] == 3
    assert [a["message"] for a in body["alerts"]] == ["Nên giảng lại N5 Con trỏ"]

    grid = {UUID(g["studentId"]): g for g in body["grid"]}
    assert len(grid) == 30
    row = grid[truot_n6[0]]
    assert row["studentName"] and row["studentCode"]  # có tên và MSSV (FR-HM-02)
    assert row["statesByKey"][N6] == "NOT_PASSED" and row["states"][str(ids[N6])] == "NOT_PASSED"
    assert row["masteredCount"] == 2 and row["progress"] == pytest.approx(2 / 11)  # N1, N3 Đạt; N5 vừa trượt
    names = [g["studentName"] for g in body["grid"]]
    assert names == sorted(names)


def test_anh_chup_khop_class_node_stats_cua_hang_doi(vi_du_6_9):
    """Ảnh chụp tính từ ma trận nhưng phải cùng số với class_node_stats do hàng đợi ghi."""
    w, ids, _ = vi_du_6_9
    from tests.unit.test_heatmap_db import stats

    st = stats(w, ids)
    nodes = {n["nodeKey"]: n for n in w.api.get(url(w, "/heatmap")).json()["nodes"]}
    for key, row in st.items():
        assert (nodes[key]["color"], nodes[key]["attemptedCount"], nodes[key]["passedCount"]) == (
            row.color,
            row.attempted_count,
            row.passed_count,
        ), key


def test_get_heatmap_khong_ghi_csdl(vi_du_6_9):
    w, ids, _ = vi_du_6_9
    from sqlalchemy import text

    before = w.db.execute(text("select count(*), max(updated_at) from class_node_stats")).one()
    w.api.get(url(w, "/heatmap"))
    w.api.get(url(w, f"/nodes/{ids[N6]}/detail"))
    assert w.db.execute(text("select count(*), max(updated_at) from class_node_stats")).one() == before


@pytest.mark.parametrize("who", ["gv_other", "sv"])
def test_chi_gv_phu_trach_lop(lop30, who):
    w, *_ = lop30
    w.current = getattr(w, who)
    r = w.api.get(url(w, "/heatmap"))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == ("NOT_CLASS_OWNER" if who == "gv_other" else "FORBIDDEN")


def test_lop_khong_ton_tai_404(lop30):
    w, *_ = lop30
    r = w.api.get(f"/api/v1/classes/{uuid4()}/heatmap")
    assert r.status_code == 404 and r.json()["error"]["code"] == "CLASS_NOT_FOUND"


def test_lop_chua_phat_hanh_cay_404(world):
    r = world.api.get(url(world, "/heatmap"))
    assert r.status_code == 404 and r.json()["error"]["code"] == "TREE_NOT_PUBLISHED"


# --- GET /classes/{id}/nodes/{n}/detail -------------------------------------------------------------------


def test_chi_tiet_nut_sv_theo_trang_thai_va_nut_goc(vi_du_6_9):
    w, ids, truot_n6 = vi_du_6_9
    r = w.api.get(url(w, f"/nodes/{ids[N6]}/detail"))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["nodeKey"] == N6 and d["rootCauseNodeId"] == str(ids[N5])
    assert d["alert"]["message"] == "Nên giảng lại N5 Con trỏ"
    assert d["stat"]["color"] == "RED"
    assert {UUID(s["studentId"]) for s in d["studentsByState"]["NOT_PASSED"]} == set(truot_n6)
    assert len(d["studentsByState"]["MASTERED"]) == 3
    assert all(s["studentName"] for group in d["studentsByState"].values() for s in group)
    assert d["topMisconceptions"] == []


def test_chi_tiet_nut_khong_thuoc_lop_404(lop30):
    w, *_ = lop30
    r = w.api.get(url(w, f"/nodes/{uuid4()}/detail"))
    assert r.status_code == 404 and r.json()["error"]["code"] == "NODE_NOT_FOUND"


def test_chi_tiet_nut_gv_khac_403(lop30):
    w, _, _, ids, _ = lop30
    w.current = w.gv_other
    r = w.api.get(url(w, f"/nodes/{ids[N1]}/detail"))
    assert r.status_code == 403 and r.json()["error"]["code"] == "NOT_CLASS_OWNER"


# --- WebSocket: quyền trên CSDL thật + MT5 ----------------------------------------------------------------


@pytest.fixture
def realtime_lop(lop30):
    """lop30 + hàng đợi đồng bộ đầy đủ như worker: tính lại → truy vết → (commit) → phát node / alert; phát cell."""
    w, svc, sv, ids, _ = lop30

    def worker(class_id: UUID, node_id: UUID) -> None:
        hs = HeatmapService(w.db)
        node = hs.recompute(class_id, node_id)
        alerts = hs.trace_root_causes(class_id)
        heatmap.push_updates(class_id, [node], alerts)

    def cell(event) -> None:
        heatmap.push_cell(event.class_id, HeatmapService(w.db).cell(event))

    heatmap.register_handlers(svc.bus, enqueue=worker, cell=cell)
    app.dependency_overrides[realtime.get_class_owner_check] = lambda: (
        lambda class_id, user: HeatmapService(w.db).require_owner(class_id, user)
    )
    yield w, svc, sv, ids
    app.dependency_overrides.pop(realtime.get_class_owner_check, None)


def subscribe(ws, channel, user_id, role=Role.LECTURER):
    ws.send_json({"action": "subscribe", "channel": channel, "token": create_access_token(user_id, role)})
    return ws.receive_json()


def test_ws_chi_gv_phu_trach_lop(realtime_lop):
    w, *_ = realtime_lop
    channel = gateway.channel_heatmap(w.class_id)
    with w.api.websocket_connect("/api/v1/ws") as ws:
        msg = subscribe(ws, channel, w.gv_other)
        assert msg["event"] == "error" and msg["payload"]["code"] == "NOT_CLASS_OWNER"
        msg = subscribe(ws, gateway.channel_heatmap(uuid4()), w.gv)
        assert msg["event"] == "error" and msg["payload"]["code"] == "CLASS_NOT_FOUND"
        msg = subscribe(ws, channel, w.sv, Role.STUDENT)
        assert msg["event"] == "error" and msg["payload"]["code"] == "FORBIDDEN"
        assert subscribe(ws, channel, w.gv)["event"] == "subscribed"


def test_mt5_o_doi_mau_trong_3_giay(realtime_lop):
    """4 SV đã thử N1 (XÁM – chưa đủ mẫu). SV thứ 5 nộp bài ⇒ đủ mẫu ⇒ GV nhận heatmap.node màu mới + heatmap.cell."""
    w, svc, sv, ids = realtime_lop
    for s in sv[:4]:
        hoc(w, svc, s, ids[N1], passed=True)
    channel = gateway.channel_heatmap(w.class_id)
    with w.api.websocket_connect("/api/v1/ws") as ws:
        assert subscribe(ws, channel, w.gv)["event"] == "subscribed"
        t0 = time.perf_counter()
        hoc(w, svc, sv[4], ids[N1], passed=True)  # start_session + apply_result → mastery.changed
        got: dict[str, dict] = {}
        while "heatmap.node" not in got or got.get("heatmap.cell", {}).get("state") != "MASTERED":
            msg = ws.receive_json()
            assert msg["channel"] == channel
            got[msg["event"]] = msg["payload"]
        elapsed = time.perf_counter() - t0
    assert elapsed <= MT5_SECONDS, f"MT5: {elapsed:.2f}s > {MT5_SECONDS}s"
    node = got["heatmap.node"]
    assert node["nodeKey"] == N1 and node["color"] == "GREEN" and node["label"] == "✓ Lớp vững – 5/5 Đạt"
    cell = got["heatmap.cell"]
    assert cell["studentId"] == str(sv[4]) and cell["nodeKey"] == N1 and cell["studentName"] == "SV 3"


def test_ws_canh_bao_nen_giang_lai(realtime_lop):
    """Ví dụ Hình 6.9 dựng qua luồng thật: lượt trượt N6 cuối cùng ⇒ heatmap.alert "Nên giảng lại …"."""
    w, svc, sv, ids = realtime_lop
    hoc_vien = sv[:6]
    for s in hoc_vien:
        for key in (N1, "n3_ham_tham_so", N5):
            hoc(w, svc, s, ids[key], passed=True)
    for s in hoc_vien[:5]:
        hoc(w, svc, s, ids[N6], passed=False)
    channel = gateway.channel_heatmap(w.class_id)
    with w.api.websocket_connect("/api/v1/ws") as ws:
        subscribe(ws, channel, w.gv)
        hoc(w, svc, hoc_vien[5], ids[N6], passed=False)
        alerts = []
        while not alerts:
            msg = ws.receive_json()
            if msg["event"] == "heatmap.alert":
                alerts.append(msg["payload"])
    assert alerts[0]["nodeKey"] == N6 and alerts[0]["message"].startswith("Nên giảng lại")
