"""C2-12 – ví dụ Hình 6.9 trên CSDL thật: HeatmapService.trace_root_causes ghi class_node_stats.root_cause_* và
trả cảnh báo "Nên giảng lại N5 Con trỏ". Cần Postgres đã migrate (TEST_DATABASE_URL).

Cây mẫu `seed/tree_ctdl_gt.json` có đúng các cạnh của Hình 6.9 (n1→n3→n5→n6, n1→n5…).
"""

from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models.enums import MasteryState
from app.services.heatmap import HeatmapService
from app.services.mastery import MasteryService
from app.services.skill_tree import SkillTreeService
from tests.unit import test_heatmap_db as _c211
from tests.unit.test_heatmap_db import hoc, stats
from tests.unit.test_tree_concurrency_db import draft
from tests.unit.test_tree_edit_db import DB_URL

world = _c211.world
lop30 = _c211.lop30
committed_world = _c211.committed_world

pytestmark = pytest.mark.skipif(not DB_URL, reason="đặt TEST_DATABASE_URL để chạy trên Postgres thật")

N1, N3, N5, N6 = "n1_bien_bo_nho", "n3_ham_tham_so", "n5_con_tro", "n6_cap_phat_dong"


def doi_rubric_n5(w):
    """Phát hành rubric mới qua API để MASTERED → NEEDS_REVERIFY theo BR-14."""
    response = w.api.post(f"/api/v1/classes/{w.class_id}/tree-versions")
    assert response.status_code == 201, response.text
    tree = response.json()
    for node in tree["nodes"]:
        rubric = node["rubric"] | {"approved": True}
        if node["key"] == N5:
            rubric["passThreshold"] = 80
        response = w.api.put(f"/api/v1/nodes/{node['id']}/rubric", json=rubric)
        assert response.status_code == 200, response.text
    response = w.api.post(f"/api/v1/tree-versions/{tree['id']}/publish")
    assert response.status_code == 200, response.text
    return {n["key"]: UUID(n["id"]) for n in response.json()["nodes"]}


@pytest.fixture
def vi_du_6_9(lop30):
    """12 SV học tới N6: 3 Đạt, 9 Chưa đạt (ĐỎ 25%). Trong 9 SV trượt, 7 SV về sau chưa Đạt N5 (r = 7/9)."""
    w, svc, sv, ids, _ = lop30
    hoc_vien = sv[:12]
    for s in hoc_vien:
        for key in (N1, N3, N5):
            hoc(w, svc, s, ids[key], passed=True)
    for i, s in enumerate(hoc_vien):
        hoc(w, svc, s, ids[N6], passed=i < 3)
    ids = doi_rubric_n5(w)
    matrix = svc.class_matrix(w.class_id)
    assert all(matrix.cells[N5][s].state == MasteryState.NEEDS_REVERIFY for s in hoc_vien)
    # Rubric đổi chưa làm mất kết quả Đạt cũ: chưa có tổ tiên đủ ngưỡng.
    before = {a.node_key: a for a in HeatmapService(w.db).trace_root_causes(w.class_id)}
    assert before[N6].is_self
    truot_n6 = hoc_vien[3:]
    for s in truot_n6[:7]:
        hoc(w, svc, s, ids[N5], passed=False)
    HeatmapService(w.db).recompute_class(w.class_id)
    return w, ids, truot_n6


def test_vi_du_6_9_canh_bao_giang_lai_n5(vi_du_6_9):
    w, ids, _ = vi_du_6_9
    alerts = {a.node_key: a for a in HeatmapService(w.db).trace_root_causes(w.class_id)}
    assert set(alerts) == {N6}  # N5 5/12 Đạt = VÀNG ⇒ không truy vết; nút khác chưa đủ mẫu
    a = alerts[N6]
    assert a.node_id == ids[N6] and a.root_cause_node_id == ids[N5] and a.root_cause_node_key == N5
    assert a.message == "Nên giảng lại N5 Con trỏ"
    assert not a.is_self and a.failed_count == 9 and a.distance == 1
    assert a.conditional_fail_rate == pytest.approx(7 / 9)
    assert a.score == pytest.approx(7 / 9 * 1.1)
    assert a.model_dump(by_alias=True)["rootCauseNodeId"] == ids[N5]  # camelCase (ApiModel)

    st = stats(w, ids)
    assert st[N6].root_cause_node_id == ids[N5]
    assert st[N6].root_cause_score == pytest.approx(7 / 9 * 1.1, rel=1e-5)
    assert all(st[k].root_cause_node_id is None for k in st if k != N6)


def test_het_nghen_o_n5_thi_n6_tu_la_diem_nghen(vi_du_6_9, monkeypatch):
    w, ids, truot_n6 = vi_du_6_9
    # Không chờ 10 phút thật; cooldown đã có test riêng trong test_mastery_db.py.
    monkeypatch.setattr("app.services.mastery.COOLDOWN", timedelta(0))
    svc = MasteryService(w.db)
    for s in truot_n6[:7]:
        hoc(w, svc, s, ids[N5], passed=True)
    alerts = HeatmapService(w.db).trace_root_causes(w.class_id)
    assert [(a.node_key, a.root_cause_node_key, a.is_self) for a in alerts] == [(N6, N6, True)]
    assert alerts[0].message == "Nên giảng lại N6 Cấp phát động (malloc/free, new/delete)"
    assert stats(w, ids)[N6].root_cause_node_id == ids[N6]


def test_nut_het_do_thi_xoa_goc_cu(vi_du_6_9, monkeypatch):
    w, ids, truot_n6 = vi_du_6_9
    monkeypatch.setattr("app.services.mastery.COOLDOWN", timedelta(0))
    mastery = MasteryService(w.db)
    svc = HeatmapService(w.db)
    svc.trace_root_causes(w.class_id)
    for s in truot_n6:  # 9 SV trượt N6 học lại N5 rồi Đạt N6 ⇒ N6 XANH
        hoc(w, mastery, s, ids[N5], passed=True)
        hoc(w, mastery, s, ids[N6], passed=True)
    svc.recompute_class(w.class_id)
    assert svc.trace_root_causes(w.class_id) == []
    st = stats(w, ids)
    assert st[N6].root_cause_node_id is None and st[N6].root_cause_score is None


@pytest.mark.parametrize("finish", ["commit", "rollback"])
def test_khoa_truy_vet_tai_nhap_va_nha_het_cuoi_giao_dich(committed_world, finish):
    """Hai kết nối thật: khóa lặp không tự chặn, kết thúc giao dịch nhả toàn bộ khóa."""
    engine, w, user = committed_world
    tree = draft(engine, w, user)
    with Session(engine) as db:
        SkillTreeService(db).publish(tree.id, user)
    with Session(engine) as first, Session(engine) as second:
        first.execute(text("SET LOCAL lock_timeout = '2s'"))
        svc = HeatmapService(first)
        svc.recompute_class(w.class_id)
        assert svc.trace_root_causes(w.class_id) == []
        assert svc.trace_root_causes(w.class_id) == []
        probe = select(func.pg_try_advisory_xact_lock(func.hashtextextended(f"heatmap:{w.class_id}", 0)))
        assert second.scalar(probe) is False
        getattr(first, finish)()
        assert second.scalar(probe) is True
