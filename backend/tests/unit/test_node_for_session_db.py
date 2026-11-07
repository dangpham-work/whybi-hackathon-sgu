"""#102 – SkillTreeService.get_node_for_session: Orchestrator không còn truy vấn thẳng ConceptNode / ClassSection.

Cần Postgres đã migrate (TEST_DATABASE_URL).
"""

from uuid import UUID, uuid4

import pytest

from app.core.errors import AppError
from app.services.skill_tree import SkillTreeService
from tests.unit import test_mastery_db as _m
from tests.unit.test_tree_edit_db import DB_URL

world = _m.world
bus = _m.bus
events = _m.events
published = _m.published

pytestmark = pytest.mark.skipif(not DB_URL, reason="đặt TEST_DATABASE_URL để chạy trên Postgres thật")


def test_tra_ve_class_id_va_nut_kem_rubric(published):
    w, tv, _ = published
    node = tv["nodes"][0]
    class_id, got = SkillTreeService(w.db).get_node_for_session(UUID(node["id"]))
    assert class_id == w.class_id
    assert got.id == UUID(node["id"])
    assert got.key == node["key"]


def test_nut_khong_ton_tai_tra_404(world):
    with pytest.raises(AppError) as e:
        SkillTreeService(world.db).get_node_for_session(uuid4())
    assert e.value.status == 404 and e.value.code == "NODE_NOT_FOUND"


def test_orchestrator_khong_import_model_cua_phan_khac():
    import app.services.session_orchestrator as orch

    assert not hasattr(orch, "ClassSection") and not hasattr(orch, "tree_orm")
