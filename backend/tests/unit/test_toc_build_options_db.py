"""Lựa chọn của GV sau cảnh báo cỡ giáo trình: mức chi tiết, hoãn sinh rubric rồi sinh bù. Cần TEST_DATABASE_URL."""

import pytest

from app.ai.agents.rubric_generator import RubricDraft
from app.services.storage import InMemoryStorage
from app.workers.documents import InMemoryJobProgress
from tests.ai.test_tree_builder import concept
from tests.unit import test_tree_edit_db as _c209
from tests.unit.test_tree_draft_db import Gateway, _doc, _drafter
from tests.unit.test_tree_edit_db import DB_URL

world = _c209.world

pytestmark = pytest.mark.skipif(not DB_URL, reason="đặt TEST_DATABASE_URL để chạy trên Postgres thật")


class CountingGateway(Gateway):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.rubric_calls = 0

    def call_json(self, schema, messages, **kw):
        if schema is RubricDraft:
            self.rubric_calls += 1
        return super().call_json(schema, messages, **kw)


def _gw():
    return CountingGateway(
        {"Chương 1": [concept("a", "A"), concept("b", "B", desc="cần A")]},
        vectors={"A": [1, 0, 0], "B": [0, 1, 0]},
        prereq={"B": [("a", True, 0.9)]},
    )


def _tree(w):
    return w.api.get(f"/api/v1/classes/{w.class_id}/tree?draft=true").json()


def test_muc_chi_tiet_dat_tran_khai_niem_moi_doan(world):
    storage = InMemoryStorage("whybi")
    drafter = _drafter(world, storage, InMemoryJobProgress(), _gw())
    drafter.run(_doc(world, storage).id, "job", None, "SUMMARY", False)
    assert drafter.builder.max_concepts == 4
    drafter2 = _drafter(world, storage, InMemoryJobProgress(), _gw())
    drafter2.run(_doc(world, storage).id, "job", None, None, False)
    assert drafter2.builder.max_concepts == 12  # không chọn ⇒ giữ mặc định cũ


def test_hoan_rubric_thi_khong_goi_ai_sinh_rubric_roi_sinh_bu_cho_nut_con_thieu(world):
    storage, gw = InMemoryStorage("whybi"), _gw()
    drafter = _drafter(world, storage, InMemoryJobProgress(), gw)
    drafter.run(_doc(world, storage).id, "job", None, "STANDARD", True)
    assert gw.rubric_calls == 0
    assert [n.get("rubric") for n in _tree(world)["nodes"]] == [None, None]

    assert drafter.fill_rubrics(world.class_id, world.gv) == 0  # 0 nút lỗi
    assert gw.rubric_calls == 2
    nodes = _tree(world)["nodes"]
    assert all(n["rubric"] and n["rubric"]["approved"] is False for n in nodes)  # sinh xong vẫn chờ GV duyệt

    assert drafter.fill_rubrics(world.class_id, world.gv) == 0
    assert gw.rubric_calls == 2  # chạy lại không sinh trùng nút đã có


def test_khong_hoan_rubric_thi_sinh_ngay_nhu_cu(world):
    storage, gw = InMemoryStorage("whybi"), _gw()
    _drafter(world, storage, InMemoryJobProgress(), gw).run(_doc(world, storage).id, "job", None, None, False)
    assert gw.rubric_calls == 2
