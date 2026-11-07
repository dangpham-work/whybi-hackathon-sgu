"""Bảo đảm đủ 28 endpoint của Bảng 5.10 luôn có trong OpenAPI (Phụ lục B kế hoạch phân công)."""

import pytest

TABLE_5_10 = [
    ("post", "/auth/login"),
    ("get", "/me"),
    ("post", "/classes"),
    ("post", "/classes/join"),
    ("post", "/classes/{class_id}/syllabi"),
    ("get", "/classes/{class_id}/tree"),
    ("post", "/tree-versions/{version_id}/nodes"),
    ("patch", "/nodes/{node_id}"),
    ("post", "/tree-versions/{version_id}/edges"),
    ("delete", "/edges/{edge_id}"),
    ("put", "/nodes/{node_id}/rubric"),
    ("post", "/nodes/{node_id}/rubric/regenerate"),
    ("post", "/tree-versions/{version_id}/publish"),
    ("get", "/classes/{class_id}/my-map"),
    ("post", "/sessions"),
    ("post", "/sessions/{session_id}/audio"),
    ("post", "/sessions/{session_id}/turns"),
    ("post", "/sessions/{session_id}/timeout"),
    ("get", "/sessions/{session_id}/result"),
    ("get", "/classes/{class_id}/heatmap"),
    ("get", "/classes/{class_id}/nodes/{node_id}/detail"),
    ("get", "/classes/{class_id}/students/{student_id}/profile"),
    ("put", "/classes/{class_id}/settings"),
    ("post", "/classes/{class_id}/matching-rounds"),
    ("put", "/enrollments/{enrollment_id}/peer-opt-in"),
    ("post", "/matches/{match_id}/{action}"),
    ("get", "/admin/flags"),
    ("put", "/admin/ai-config"),
]


@pytest.fixture(scope="module")
def paths(client):
    return client.get("/openapi.json").json()["paths"]


@pytest.mark.parametrize(("method", "path"), TABLE_5_10)
def test_endpoint_declared(paths, method, path):
    full = "/api/v1" + path
    assert full in paths, f"thiếu {full}"
    assert method in paths[full]


def test_table_has_28_endpoints():
    assert len(TABLE_5_10) == 28
