"""C2-09 – Xong khi: thêm cạnh tạo chu trình bị từ chối kèm đường đi; phát hành tạo phiên bản cây.

Cần Postgres đã migrate (TEST_DATABASE_URL – CI job backend đặt sẵn). Mỗi test chạy trong một transaction rollback.
Người dùng hiện tại giả lập bằng ghi đè `get_current_user` (xác thực thật: C2-07).
"""

import json
import os
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.db.session import get_db
from app.main import app
from app.models.enums import Role
from app.models.users import ClassSection, Course, Enrollment, Lecturer, Student, User
from app.services.skill_tree import seed_dir

DB_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="đặt TEST_DATABASE_URL để chạy trên Postgres thật")

SEED = json.loads((seed_dir() / "tree_ctdl_gt.json").read_text(encoding="utf-8"))


class World:
    """Dữ liệu tối thiểu: GV chủ lớp, GV khác, SV đã tham gia, SV ngoài lớp, một lớp."""

    def __init__(self, db):
        def user(role: Role, name: str) -> UUID:
            u = User(id=uuid4(), full_name=name, email=f"{uuid4().hex[:8]}@whybi.test", password_hash="x", role=role)
            db.add(u)
            db.flush()
            if role == Role.LECTURER:
                db.add(Lecturer(user_id=u.id))
            elif role == Role.STUDENT:
                db.add(Student(user_id=u.id, student_code=uuid4().hex[:10]))
            db.flush()
            return u.id

        self.gv = user(Role.LECTURER, "GV chủ lớp")
        self.gv_other = user(Role.LECTURER, "GV khác")
        self.sv = user(Role.STUDENT, "SV trong lớp")
        self.sv_out = user(Role.STUDENT, "SV ngoài lớp")
        course = Course(id=uuid4(), code=uuid4().hex[:8], name="CTDL&GT")
        db.add(course)
        db.flush()
        self.class_id = uuid4()
        db.add(
            ClassSection(
                id=self.class_id,
                course_id=course.id,
                lecturer_id=self.gv,
                name="CTDL&GT – Nhóm 02",
                semester="HK1",
                join_code=uuid4().hex[:8].upper(),
            )
        )
        db.flush()
        db.add(Enrollment(class_id=self.class_id, student_id=self.sv))
        db.flush()
        self.roles = {self.gv: Role.LECTURER, self.gv_other: Role.LECTURER, self.sv: Role.STUDENT}
        self.roles[self.sv_out] = Role.STUDENT
        self.current = self.gv


@pytest.fixture
def world():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    engine = create_engine(DB_URL)
    conn = engine.connect()
    tx = conn.begin()
    db = Session(bind=conn, join_transaction_mode="create_savepoint")
    w = World(db)
    w.db = db
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[deps.get_current_user] = lambda: deps.CurrentUser(id=w.current, role=w.roles[w.current])
    w.api = TestClient(app)
    yield w
    app.dependency_overrides.clear()
    db.close()
    tx.rollback()
    conn.close()
    engine.dispose()


def _import_seed(w, **params):
    r = w.api.post(f"/api/v1/classes/{w.class_id}/tree-versions", json=SEED, params=params)
    assert r.status_code == 201, r.text
    return r.json()


def _key_to_id(tree: dict) -> dict[str, str]:
    return {n["key"]: n["id"] for n in tree["nodes"]}


def _approve_all(w, tree):
    rubric = next(n["rubric"] for n in SEED["nodes"] if n.get("rubric"))
    for n in tree["nodes"]:
        r = w.api.put(f"/api/v1/nodes/{n['id']}/rubric", json=rubric | {"approved": True})
        assert r.status_code == 200, r.text


# --- Nhập cây, đọc cây ---------------------------------------------------------------------------


def test_import_seed_tree_as_draft(world):
    tv = _import_seed(world)
    assert tv["versionNo"] == 1 and tv["status"] == "DRAFT" and tv["classId"] == str(world.class_id)
    assert len(tv["nodes"]) == 11 and len(tv["edges"]) == 13
    n5 = next(n for n in tv["nodes"] if n["code"] == "N5")
    assert [kp["id"] for kp in n5["rubric"]["keyPoints"]] == ["KP1", "KP2", "KP3"]
    assert n5["rubric"]["sourcePages"] == [43, 44, 45, 46, 47]
    assert n5["rubric"]["approved"] is False, "cây nhập vào luôn chờ GV duyệt rubric (seed ghi approved=true)"


def test_import_with_sanitize_drops_transitive_edge(world):
    """N1→N5 là cạnh bắc cầu (đã có N1→N3→N5) – sanitize (6.1.4) bỏ cạnh đó."""
    tv = _import_seed(world, sanitize="true")
    edges = {(e["fromKey"], e["toKey"]) for e in tv["edges"]}
    assert ("n1_bien_bo_nho", "n5_con_tro") not in edges and len(edges) == 12


def test_import_cyclic_tree_rejected_with_path(world):
    body = SEED | {"edges": [*SEED["edges"], {"fromKey": "n11_avl", "toKey": "n1_bien_bo_nho"}]}
    r = world.api.post(f"/api/v1/classes/{world.class_id}/tree-versions", json=body)
    assert r.status_code == 409 and r.json()["error"]["code"] == "CYCLE_DETECTED"
    assert r.json()["error"]["details"]["path"][0] == r.json()["error"]["details"]["path"][-1]


def test_get_tree_draft_for_owner_only(world):
    _import_seed(world)
    url = f"/api/v1/classes/{world.class_id}/tree"
    assert world.api.get(url, params={"draft": "true"}).json()["versionNo"] == 1
    r = world.api.get(url)
    assert r.status_code == 404 and r.json()["error"]["code"] == "TREE_NOT_PUBLISHED"
    world.current = world.gv_other
    assert world.api.get(url, params={"draft": "true"}).status_code == 403


# --- Sửa nút ---------------------------------------------------------------------------------------


def test_add_and_patch_node(world):
    tv = _import_seed(world)
    r = world.api.post(
        f"/api/v1/tree-versions/{tv['id']}/nodes", json={"key": "n12_heap", "title": "Heap", "code": "N12"}
    )
    assert r.status_code == 201 and r.json()["id"]
    dup = world.api.post(f"/api/v1/tree-versions/{tv['id']}/nodes", json={"key": "n12_heap", "title": "Heap 2"})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "NODE_KEY_EXISTS"
    p = world.api.patch(f"/api/v1/nodes/{r.json()['id']}", json={"positionX": 120.5, "positionY": 40})
    assert p.status_code == 200 and p.json()["positionX"] == 120.5 and p.json()["title"] == "Heap"


def test_other_lecturer_cannot_edit(world):
    tv = _import_seed(world)
    world.current = world.gv_other
    r = world.api.post(f"/api/v1/tree-versions/{tv['id']}/nodes", json={"key": "x", "title": "X"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "NOT_CLASS_OWNER"


# --- Cạnh: chặn chu trình (FR-SK-07, TC03) --------------------------------------------------------


def test_add_edge_creating_cycle_rejected_with_path(world):
    tv = _import_seed(world)
    r = world.api.post(
        f"/api/v1/tree-versions/{tv['id']}/edges", json={"fromKey": "n6_cap_phat_dong", "toKey": "n5_con_tro"}
    )
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "CYCLE_DETECTED"
    assert err["details"]["path"] == ["n6_cap_phat_dong", "n5_con_tro", "n6_cap_phat_dong"]


def test_add_valid_edge_then_duplicate_then_delete(world):
    tv = _import_seed(world)
    url = f"/api/v1/tree-versions/{tv['id']}/edges"
    body = {"fromKey": "n2_mang", "toKey": "n11_avl", "source": "AI", "confidence": 0.4}
    r = world.api.post(url, json=body)
    assert r.status_code == 201
    assert r.json()["source"] == "LECTURER", "cạnh GV tự nối luôn là LECTURER"
    dup = world.api.post(url, json=body)
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "EDGE_EXISTS"
    assert world.api.delete(f"/api/v1/edges/{r.json()['id']}").status_code == 204
    assert world.api.delete(f"/api/v1/edges/{r.json()['id']}").status_code == 404


def test_edge_to_unknown_node(world):
    tv = _import_seed(world)
    r = world.api.post(f"/api/v1/tree-versions/{tv['id']}/edges", json={"fromKey": "n2_mang", "toKey": "khong_co"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "NODE_NOT_FOUND"


# --- Rubric, phát hành (BR-05) --------------------------------------------------------------------


def test_publish_rejected_until_all_rubrics_approved(world):
    tv = _import_seed(world)
    r = world.api.post(f"/api/v1/tree-versions/{tv['id']}/publish")
    assert r.status_code == 422 and r.json()["error"]["code"] == "PUBLISH_CHECK_FAILED"
    problems = r.json()["error"]["details"]["errors"]
    # Cây nhập vào chưa duyệt rubric nào (kể cả N5 dù seed ghi approved=true)
    assert {p["nodeKey"] for p in problems if p["code"] == "RUBRIC_NOT_APPROVED"} == {n["key"] for n in SEED["nodes"]}


def test_publish_creates_version_and_freezes_it(world):
    tv = _import_seed(world)
    _approve_all(world, tv)
    r = world.api.post(f"/api/v1/tree-versions/{tv['id']}/publish")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "PUBLISHED" and r.json()["publishedAt"]
    # Bản đã phát hành không sửa được nữa
    again = world.api.post(f"/api/v1/tree-versions/{tv['id']}/nodes", json={"key": "x", "title": "X"})
    assert again.status_code == 409 and again.json()["error"]["code"] == "VERSION_NOT_EDITABLE"
    # SV trong lớp thấy cây đã phát hành; SV ngoài lớp thì không
    world.current = world.sv
    got = world.api.get(f"/api/v1/classes/{world.class_id}/tree")
    assert got.status_code == 200 and got.json()["status"] == "PUBLISHED"
    world.current = world.sv_out
    assert world.api.get(f"/api/v1/classes/{world.class_id}/tree").status_code == 403


def test_new_draft_from_published_then_publish_archives_old(world):
    tv = _import_seed(world)
    _approve_all(world, tv)
    world.api.post(f"/api/v1/tree-versions/{tv['id']}/publish")
    r = world.api.post(f"/api/v1/classes/{world.class_id}/tree-versions")
    assert r.status_code == 201
    v2 = r.json()
    assert v2["versionNo"] == 2 and v2["status"] == "DRAFT"
    assert set(_key_to_id(v2)) == set(_key_to_id(tv)) and set(_key_to_id(v2).values()).isdisjoint(
        _key_to_id(tv).values()
    )
    assert all(n["rubric"]["approved"] for n in v2["nodes"])
    pub = world.api.post(f"/api/v1/tree-versions/{v2['id']}/publish")
    assert pub.status_code == 200 and pub.json()["versionNo"] == 2
    got = world.api.get(f"/api/v1/classes/{world.class_id}/tree").json()
    assert got["versionNo"] == 2


def test_put_rubric_roundtrip(world):
    tv = _import_seed(world)
    n2 = next(n for n in tv["nodes"] if n["key"] == "n2_mang")
    rubric = {
        "keyPoints": [{"id": "KP1", "content": "Mảng là dãy phần tử liên tiếp cùng kiểu."}],
        "misconceptions": [{"id": "MC1", "content": "Chỉ số mảng bắt đầu từ 1.", "isCritical": True}],
        "scenarios": [
            {"id": "SC1", "scenario": "a[5] với mảng 5 phần tử?", "bloomLevel": "APPLY", "expectedPoints": "tràn"}
        ],
        "passThreshold": 75,
        "sourcePages": [12],
    }
    r = world.api.put(f"/api/v1/nodes/{n2['id']}/rubric", json=rubric)
    assert r.status_code == 200
    body = r.json()
    assert body["approved"] is False and body["passThreshold"] == 75
    assert body["scenarios"][0]["expectedPoints"] == "tràn"
    tree = world.api.get(f"/api/v1/classes/{world.class_id}/tree", params={"draft": "true"}).json()
    assert next(n for n in tree["nodes"] if n["key"] == "n2_mang")["rubric"]["keyPoints"][0]["id"] == "KP1"


def test_patch_required_field_to_null_is_422(world):
    tv = _import_seed(world)
    r = world.api.patch(f"/api/v1/nodes/{tv['nodes'][0]['id']}", json={"title": None})
    assert r.status_code == 422


def test_import_tree_with_unknown_edge_key_is_422(world):
    body = SEED | {"edges": [{"fromKey": "n1_bien_bo_nho", "toKey": "khong_co"}]}
    r = world.api.post(f"/api/v1/classes/{world.class_id}/tree-versions", json=body)
    assert r.status_code == 422


def test_delete_node_reconnects_prerequisites_without_duplicates_and_rejects_published(world):
    tv = _import_seed(world)
    by_key = _key_to_id(tv)
    # Xóa n3 (giữa n1 → n3 → n5, khi n1 → n5 đã có sẵn): không tạo cạnh trùng n1 → n5
    r1 = world.api.delete(f"/api/v1/nodes/{by_key['n3_ham_tham_so']}")
    assert r1.status_code == 200, r1.text
    after_n3 = r1.json()
    assert "n3_ham_tham_so" not in {n["key"] for n in after_n3["nodes"]}
    pairs_n3 = [(e["fromKey"], e["toKey"]) for e in after_n3["edges"]]
    assert pairs_n3.count(("n1_bien_bo_nho", "n5_con_tro")) == 1

    # Xóa n5 (giữa n1 → n5 → n6, n7): tự nối n1 → n6 và n1 → n7
    r2 = world.api.delete(f"/api/v1/nodes/{by_key['n5_con_tro']}")
    assert r2.status_code == 200, r2.text
    after_n5 = r2.json()
    pairs_n5 = {(e["fromKey"], e["toKey"]) for e in after_n5["edges"]}
    assert ("n1_bien_bo_nho", "n6_cap_phat_dong") in pairs_n5
    assert ("n1_bien_bo_nho", "n7_dslk_don") in pairs_n5

    # Bản đã phát hành: chặn xóa nút
    _approve_all(world, after_n5)
    world.api.post(f"/api/v1/tree-versions/{after_n5['id']}/publish")
    locked = world.api.delete(f"/api/v1/nodes/{by_key['n1_bien_bo_nho']}")
    assert locked.status_code == 409 and locked.json()["error"]["code"] == "VERSION_NOT_EDITABLE"


def test_merge_nodes_modes_and_cycle_rejection(world):
    tv = _import_seed(world)
    vid = tv["id"]
    # Gộp n1 và n5 khi có đường n1 → n3 → n5 sẽ tạo chu trình n1 → n3 → n1 ⇒ 409 CYCLE_DETECTED
    cyc = world.api.post(
        f"/api/v1/tree-versions/{vid}/merge-nodes",
        json={"firstKey": "n1_bien_bo_nho", "secondKey": "n5_con_tro", "mode": "FIRST"},
    )
    assert cyc.status_code == 409 and cyc.json()["error"]["code"] == "CYCLE_DETECTED"

    # Gộp hai nút kề nhau n2_mang và n4_de_quy (không có nút trung gian) với mode=CUSTOM
    ok_res = world.api.post(
        f"/api/v1/tree-versions/{vid}/merge-nodes",
        json={
            "firstKey": "n2_mang",
            "secondKey": "n4_de_quy",
            "mode": "CUSTOM",
            "title": "Mảng và Đệ quy",
            "chapterRef": "Chương 2-3",
            "bloomLevel": "APPLY",
        },
    )
    assert ok_res.status_code == 200, ok_res.text
    merged = ok_res.json()
    keys = {n["key"]: n for n in merged["nodes"]}
    assert "n4_de_quy" not in keys and keys["n2_mang"]["title"] == "Mảng và Đệ quy"
    assert keys["n2_mang"]["bloomLevel"] == "APPLY"
    edges = {(e["fromKey"], e["toKey"]) for e in merged["edges"]}
    assert ("n3_ham_tham_so", "n2_mang") in edges

    # Bản đã phát hành: chặn gộp nút
    _approve_all(world, merged)
    world.api.post(f"/api/v1/tree-versions/{vid}/publish")
    locked = world.api.post(
        f"/api/v1/tree-versions/{vid}/merge-nodes",
        json={"firstKey": "n1_bien_bo_nho", "secondKey": "n2_mang", "mode": "SECOND"},
    )
    assert locked.status_code == 409 and locked.json()["error"]["code"] == "VERSION_NOT_EDITABLE"
