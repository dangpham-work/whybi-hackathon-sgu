def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_error_format_is_unified(client):
    """Mục 5.4.1: mọi lỗi có dạng {"error": {"code", "message", "details"}}."""
    r = client.get("/api/v1/me")
    assert r.status_code == 401
    assert set(r.json()["error"]) == {"code", "message", "details"}
