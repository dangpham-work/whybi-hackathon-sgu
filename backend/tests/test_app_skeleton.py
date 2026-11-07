"""C2-01: khung ứng dụng – router tự nạp, /health, định dạng lỗi 501 cho endpoint chưa làm."""

from pathlib import Path

import pytest
from fastapi import FastAPI

from app.main import include_routers

ROUTER_MODULES = {"admin", "auth", "classes", "heatmap", "matching", "realtime", "sessions", "trees"}


def test_include_routers_loads_every_api_module():
    """Mọi module trong app/api/ có biến `router` đều được gắn; bỏ qua deps và module bắt đầu bằng _."""
    app = FastAPI()
    loaded = include_routers(app, "/api/v1")
    assert set(loaded) == ROUTER_MODULES
    assert "deps" not in loaded


def test_all_api_routes_use_prefix(client):
    paths = client.get("/openapi.json").json()["paths"]
    api_paths = [p for p in paths if p != "/health"]
    assert api_paths, "không có router nào được nạp"
    assert all(p.startswith("/api/v1/") for p in api_paths)


def test_openapi_has_at_least_28_endpoints(client):
    """Bảng 5.10 có 28 endpoint; router còn có thêm đường dẫn vòng 2 (lịch sử phiên bản…)."""
    paths = client.get("/openapi.json").json()["paths"]
    operations = [(m, p) for p, ops in paths.items() if p.startswith("/api/v1/") for m in ops]
    assert len(operations) >= 28


def test_health_reports_env_and_fake_llm(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body == {"status": "ok", "env": "test", "llm_mode": "fake"}


def test_health_needs_no_auth(client):
    """Healthcheck của Docker / Nginx gọi không kèm token."""
    assert client.get("/health", headers={}).status_code == 200


def test_unknown_route_uses_error_format(client):
    r = client.get("/api/v1/khong-ton-tai")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_repo_has_ci_and_review_files():
    """Mục 7.1–7.2: CI chạy ruff, pytest, tsc, build; có AGENTS.md, CODEOWNERS, mẫu PR."""
    root = Path(__file__).resolve().parents[2]
    if not (root / ".github").is_dir():
        pytest.skip("chạy trong image backend – không có thư mục gốc repo")
    ci = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    for step in ("ruff check", "ruff format --check", "pytest", "npm run typecheck", "npm test", "npm run build"):
        assert step in ci, f"CI thiếu bước: {step}"
    for f in ("AGENTS.md", ".github/CODEOWNERS", ".github/pull_request_template.md", "docker-compose.yml"):
        assert (root / f).is_file(), f"thiếu {f}"
