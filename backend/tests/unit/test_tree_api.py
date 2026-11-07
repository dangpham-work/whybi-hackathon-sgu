"""C2-02 – Xong khi: Đăng và Thắng lấy được cây mẫu qua API (GET /classes/{id}/tree)."""

import pytest
from pydantic import ValidationError

from app.algorithms.dag import build_graph, find_cycle
from app.models.schemas.tree import Edge, Node, TreeVersion
from app.services.skill_tree import SEED_CLASS_ID

URL = f"/api/v1/classes/{SEED_CLASS_ID}/tree"
LECTURER = {"Authorization": "Bearer dev-lecturer"}
STUDENT = {"Authorization": "Bearer dev-student"}
ADMIN = {"Authorization": "Bearer dev-admin"}


@pytest.fixture(scope="module")
def tree_json(client):
    r = client.get(URL, headers=LECTURER)
    assert r.status_code == 200, r.text
    return r.json()


def _keys(obj):
    """Mọi khóa JSON lồng nhau."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v)


def test_seed_tree_matches_schema(tree_json):
    tv = TreeVersion.model_validate(tree_json)
    assert len(tv.nodes) == 11
    assert len(tv.edges) == 13
    assert tv.class_id == SEED_CLASS_ID
    assert tv.id is not None and all(n.id is not None for n in tv.nodes)


def test_seed_tree_is_dag(tree_json):
    tv = TreeVersion.model_validate(tree_json)
    g = build_graph(tv)
    assert g.number_of_nodes() == 11
    assert find_cycle(g) is None


def test_json_is_camel_case(tree_json):
    keys = set(_keys(tree_json))
    assert {"classId", "versionNo", "fromKey", "toKey", "bloomLevel", "keyPoints", "passThreshold"} <= keys
    assert not [k for k in keys if "_" in k], "có khóa snake_case trong JSON"


def test_n5_has_rubric_from_table_6_1(tree_json):
    n5 = next(n for n in tree_json["nodes"] if n["code"] == "N5")
    assert n5["key"] == "n5_con_tro"
    assert [kp["id"] for kp in n5["rubric"]["keyPoints"]] == ["KP1", "KP2", "KP3"]


def test_ids_are_stable_between_calls(client, tree_json):
    again = client.get(URL, headers=LECTURER).json()
    assert [n["id"] for n in again["nodes"]] == [n["id"] for n in tree_json["nodes"]]


def test_student_can_read_tree(client):
    assert client.get(URL, headers=STUDENT).status_code == 200


def test_admin_forbidden(client):
    r = client.get(URL, headers=ADMIN)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"


def test_requires_token(client):
    assert client.get(URL).status_code == 401


def test_unknown_class_404(client):
    r = client.get("/api/v1/classes/00000000-0000-0000-0000-000000000000/tree", headers=LECTURER)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "CLASS_NOT_FOUND"


# --- Ràng buộc của schema TreeVersion -------------------------------------------------------


def _nodes(*keys):
    return [Node(key=k, title=k.upper()) for k in keys]


def test_edge_must_reference_existing_node():
    with pytest.raises(ValidationError, match="không có trong danh sách nút"):
        TreeVersion(nodes=_nodes("a"), edges=[Edge(from_key="a", to_key="b")])


def test_duplicate_node_key_rejected():
    with pytest.raises(ValidationError, match="trùng"):
        TreeVersion(nodes=_nodes("a", "a"), edges=[])


def test_self_loop_rejected():
    with pytest.raises(ValidationError, match="tự trỏ"):
        TreeVersion(nodes=_nodes("a"), edges=[Edge(from_key="a", to_key="a")])


def test_find_cycle_returns_path():
    tv = TreeVersion(
        nodes=_nodes("a", "b", "c"),
        edges=[Edge(from_key="a", to_key="b"), Edge(from_key="b", to_key="c"), Edge(from_key="c", to_key="a")],
    )
    path = find_cycle(build_graph(tv))
    assert path is not None and set(path) == {"a", "b", "c"}


def test_dev_token_rejected_outside_dev(monkeypatch):
    """Token dev-* chỉ dùng tạm tới C2-07, không bao giờ có hiệu lực ở demo / prod."""
    from types import SimpleNamespace

    from app.api import deps

    def env(**kw):
        cfg = {"allow_dev_tokens": True, "demo_mode": False, "app_env": "dev"} | kw
        monkeypatch.setattr(deps, "get_settings", lambda: SimpleNamespace(**cfg))

    env()
    assert deps._dev_user("dev-lecturer").role == "LECTURER"
    assert deps._dev_user("token-la") is None
    env(app_env="prod")
    assert deps._dev_user("dev-lecturer") is None
    env(app_env="demo")
    assert deps._dev_user("dev-lecturer") is None
    env(demo_mode=True)
    assert deps._dev_user("dev-lecturer") is None
    env(allow_dev_tokens=False)  # mặc định của Settings
    assert deps._dev_user("dev-lecturer") is None
