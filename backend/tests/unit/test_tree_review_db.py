"""C2-23 – duyệt cây lớn: rubric hợp lệ mới được duyệt, duyệt hàng loạt, kiểm tra trước khi phát hành, ghi chú
phát hành, lịch sử phiên bản dạng tóm tắt, lưu vị trí hàng loạt. Cần TEST_DATABASE_URL."""

from uuid import uuid4

import pytest

from tests.unit import test_tree_edit_db as _c209
from tests.unit.test_tree_edit_db import DB_URL, SEED, _import_seed, _key_to_id

world = _c209.world

pytestmark = pytest.mark.skipif(not DB_URL, reason="đặt TEST_DATABASE_URL để chạy trên Postgres thật")

GOOD = next(n["rubric"] for n in SEED["nodes"] if n.get("rubric"))
EMPTY = {**GOOD, "keyPoints": [], "approved": False}
BLANK = {**GOOD, "keyPoints": [{"id": "KP1", "content": "   ", "isRequired": True}], "approved": False}
OPTIONAL_ONLY = {**GOOD, "keyPoints": [{"id": "KP1", "content": "ý phụ", "isRequired": False}], "approved": False}
TOO_MANY_PASS = {**GOOD, "minChallenges": 2, "minPassedChallenges": 3, "approved": False}


def _put(w, node_id, rubric):
    return w.api.put(f"/api/v1/nodes/{node_id}/rubric", json=rubric)


@pytest.mark.parametrize("bad", [EMPTY, BLANK, OPTIONAL_ONLY, TOO_MANY_PASS])
def test_khong_duyet_duoc_rubric_khong_hop_le_nhung_luu_nhap_duoc(world, bad):
    tv = _import_seed(world)
    nid = tv["nodes"][0]["id"]
    assert _put(world, nid, bad).status_code == 200  # lưu nháp thì được
    r = _put(world, nid, {**bad, "approved": True})
    assert r.status_code == 422 and r.json()["error"]["code"] == "RUBRIC_INVALID"
    assert r.json()["error"]["details"]["problems"]


def test_duyet_hang_loat_chi_duyet_rubric_hop_le_va_noi_ly_do(world):
    tv = _import_seed(world)
    ids = _key_to_id(tv)
    bad_id = ids["n2_mang"]
    _put(world, bad_id, EMPTY)
    r = world.api.post(f"/api/v1/classes/{world.class_id}/tree/rubrics/approve", json={"nodeIds": list(ids.values())})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["approved"]) == len(ids) - 1 and bad_id not in body["approved"]
    assert [x["nodeId"] for x in body["rejected"]] == [bad_id] and body["rejected"][0]["reason"]
    tree = world.api.get(f"/api/v1/classes/{world.class_id}/tree?draft=true").json()
    assert {n["key"] for n in tree["nodes"] if n["rubric"]["approved"]} == set(ids) - {"n2_mang"}


def test_duyet_hang_loat_chi_gv_chu_lop_va_nut_khong_thuoc_lop(world):
    tv = _import_seed(world)
    url = f"/api/v1/classes/{world.class_id}/tree/rubrics/approve"
    world.current = world.gv_other
    assert world.api.post(url, json={"nodeIds": [tv["nodes"][0]["id"]]}).status_code == 403
    world.current = world.gv
    r = world.api.post(url, json={"nodeIds": [str(uuid4())]})
    assert r.status_code == 200 and r.json()["approved"] == [] and r.json()["rejected"][0]["reason"]


def test_kiem_tra_truoc_khi_phat_hanh(world):
    tv = _import_seed(world)
    ids = _key_to_id(tv)
    _put(world, ids["n2_mang"], EMPTY)
    world.api.post(
        f"/api/v1/classes/{world.class_id}/tree/rubrics/approve",
        json={"nodeIds": [i for k, i in ids.items() if k != "n2_mang"]},
    )
    r = world.api.get(f"/api/v1/classes/{world.class_id}/tree/publish-check")
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["ok"] is False and c["versionId"] == tv["id"]
    assert c["unapprovedCount"] == 1 and c["affectedStudents"] == 1 and c["olderThanPublished"] is False
    assert [e["nodeKey"] for e in c["errors"] if e["code"] == "RUBRIC_NOT_APPROVED"] == ["n2_mang"]
    world.current = world.gv_other
    assert world.api.get(f"/api/v1/classes/{world.class_id}/tree/publish-check").status_code == 403


def test_kiem_tra_dat_thi_ok_va_phat_hanh_luu_ghi_chu(world):
    tv = _import_seed(world)
    ids = _key_to_id(tv)
    world.api.post(f"/api/v1/classes/{world.class_id}/tree/rubrics/approve", json={"nodeIds": list(ids.values())})
    assert world.api.get(f"/api/v1/classes/{world.class_id}/tree/publish-check").json()["ok"] is True
    r = world.api.post(f"/api/v1/tree-versions/{tv['id']}/publish", json={"changeNote": "Học kỳ 1 – bỏ chương ôn tập"})
    assert r.status_code == 200 and r.json()["changeNote"] == "Học kỳ 1 – bỏ chương ôn tập"


def test_phat_hanh_khong_gui_than_van_duoc(world):
    tv = _import_seed(world)
    world.api.post(
        f"/api/v1/classes/{world.class_id}/tree/rubrics/approve", json={"nodeIds": [n["id"] for n in tv["nodes"]]}
    )
    assert world.api.post(f"/api/v1/tree-versions/{tv['id']}/publish").status_code == 200


def test_lich_su_phien_ban_chi_tra_tom_tat_khong_kem_ca_cay(world):
    tv = _import_seed(world)
    world.api.post(
        f"/api/v1/classes/{world.class_id}/tree/rubrics/approve", json={"nodeIds": [n["id"] for n in tv["nodes"]]}
    )
    world.api.post(f"/api/v1/tree-versions/{tv['id']}/publish", json={"changeNote": "bản đầu"})
    rows = world.api.get(f"/api/v1/classes/{world.class_id}/tree-versions").json()
    assert len(rows) == 1
    v = rows[0]
    assert v["versionNo"] == 1 and v["status"] == "PUBLISHED" and v["changeNote"] == "bản đầu"
    assert v["nodeCount"] == 11 and v["edgeCount"] == 13 and v["publishedAt"]
    assert "nodes" not in v and "edges" not in v


def test_luu_vi_tri_hang_loat(world):
    tv = _import_seed(world)
    ids = _key_to_id(tv)
    body = {"positions": [{"nodeId": i, "x": 10.5 * n, "y": 20.0} for n, i in enumerate(ids.values())]}
    r = world.api.put(f"/api/v1/tree-versions/{tv['id']}/positions", json=body)
    assert r.status_code == 204, r.text
    tree = world.api.get(f"/api/v1/classes/{world.class_id}/tree?draft=true").json()
    assert all(n["positionY"] == 20.0 and n["positionX"] is not None for n in tree["nodes"])
    bad = {"positions": [{"nodeId": str(uuid4()), "x": 1, "y": 1}]}
    assert world.api.put(f"/api/v1/tree-versions/{tv['id']}/positions", json=bad).status_code == 404
    world.current = world.gv_other
    assert world.api.put(f"/api/v1/tree-versions/{tv['id']}/positions", json=body).status_code == 403
