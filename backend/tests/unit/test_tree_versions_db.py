"""C2-16 – Xong khi: khôi phục phiên bản cũ thành bản nháp mới (FR-SK-10); xem lịch sử, so sánh hai phiên bản."""

import pytest

from tests.unit.test_tree_edit_db import DB_URL, _approve_all, _import_seed, world  # noqa: F401

pytestmark = pytest.mark.skipif(not DB_URL, reason="đặt TEST_DATABASE_URL để chạy trên Postgres thật")

API = "/api/v1"


def _publish(w, tv):
    _approve_all(w, tv)
    r = w.api.post(f"{API}/tree-versions/{tv['id']}/publish")
    assert r.status_code == 200, r.text


def test_list_versions_newest_first_owner_only(world):  # noqa: F811
    v1 = _import_seed(world)
    _publish(world, v1)
    v2 = world.api.post(f"{API}/classes/{world.class_id}/tree-versions").json()
    r = world.api.get(f"{API}/classes/{world.class_id}/tree-versions")
    assert r.status_code == 200
    assert [v["versionNo"] for v in r.json()] == [2, 1]
    assert r.json()[0]["id"] == v2["id"] and r.json()[1]["status"] == "PUBLISHED"
    world.current = world.gv_other
    assert world.api.get(f"{API}/classes/{world.class_id}/tree-versions").status_code == 403


def test_restore_old_version_becomes_new_draft(world):  # noqa: F811
    v1 = _import_seed(world)
    _publish(world, v1)
    # bản 2: thêm nút rồi bỏ đi bằng cách khôi phục bản 1
    v2 = world.api.post(f"{API}/classes/{world.class_id}/tree-versions").json()
    world.api.post(f"{API}/tree-versions/{v2['id']}/nodes", json={"key": "n12_heap", "title": "Heap"})
    r = world.api.post(f"{API}/tree-versions/{v1['id']}/restore")
    assert r.status_code == 201, r.text
    v3 = r.json()
    assert v3["versionNo"] == 3 and v3["status"] == "DRAFT"
    assert "1" in v3["changeNote"]
    assert {n["key"] for n in v3["nodes"]} == {n["key"] for n in v1["nodes"]}
    assert len(v3["edges"]) == len(v1["edges"])
    # bản gốc không bị đổi
    assert world.api.get(f"{API}/classes/{world.class_id}/tree").json()["versionNo"] == 1
    world.current = world.gv_other
    assert world.api.post(f"{API}/tree-versions/{v1['id']}/restore").status_code == 403


def test_restore_unknown_version_404(world):  # noqa: F811
    r = world.api.post(f"{API}/tree-versions/00000000-0000-0000-0000-000000000001/restore")
    assert r.status_code == 404 and r.json()["error"]["code"] == "VERSION_NOT_FOUND"


def test_compare_two_versions(world):  # noqa: F811
    v1 = _import_seed(world)
    _publish(world, v1)
    v2 = world.api.post(f"{API}/classes/{world.class_id}/tree-versions").json()
    world.api.post(f"{API}/tree-versions/{v2['id']}/nodes", json={"key": "n12_heap", "title": "Heap"})
    n1 = next(n for n in v2["nodes"] if n["code"] == "N1")
    world.api.patch(f"{API}/nodes/{n1['id']}", json={"title": "Biến và bộ nhớ (sửa)"})
    edge = v2["edges"][0]
    world.api.delete(f"{API}/edges/{edge['id']}")
    r = world.api.get(f"{API}/tree-versions/{v1['id']}/compare/{v2['id']}")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["fromVersionNo"] == 1 and d["toVersionNo"] == 2
    assert d["nodesAdded"] == ["n12_heap"] and d["nodesRemoved"] == []
    assert d["nodesChanged"] == [n1["key"]]
    assert d["edgesRemoved"] == [{"fromKey": edge["fromKey"], "toKey": edge["toKey"]}] and d["edgesAdded"] == []
    world.current = world.gv_other
    assert world.api.get(f"{API}/tree-versions/{v1['id']}/compare/{v2['id']}").status_code == 403
