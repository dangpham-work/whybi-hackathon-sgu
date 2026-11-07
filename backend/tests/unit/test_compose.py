"""C2-03 – docker-compose.yml đủ dịch vụ theo Bảng 5.15 và chạy được trên máy mới.

Test tĩnh (đọc tệp). Chạy thật: `docker compose up -d --build --wait` (job CI `e2e`).
"""

import re
from pathlib import Path
from urllib.parse import urlparse

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parents[3]
COMPOSE = ROOT / "docker-compose.yml"

if not COMPOSE.is_file():
    pytest.skip("chạy trong image backend – không có docker-compose.yml", allow_module_level=True)


@pytest.fixture(scope="module")
def services() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]


def test_all_services_of_table_5_15(services):
    assert {"nginx", "api", "worker", "beat", "postgres", "redis", "minio", "stt"} <= set(services)


def test_stt_is_optional_profile(services):
    assert services["stt"]["profiles"] == ["stt"]
    always_on = [name for name, s in services.items() if "profiles" not in s]
    assert "stt" not in always_on


def test_api_runs_4_uvicorn_workers_after_migration(services):
    cmd = services["api"]["command"]
    assert "alembic upgrade head" in cmd
    assert "--workers 4" in cmd


def test_worker_listens_to_4_queues(services):
    cmd = services["worker"]["command"]
    queues = re.search(r"-Q\s+(\S+)", cmd).group(1).split(",")
    assert set(queues) == {"documents", "aggregation", "matching", "ai"}
    assert "beat" in services["beat"]["command"]


def test_images_postgres16_pgvector_and_redis7(services):
    assert services["postgres"]["image"].startswith("pgvector/pgvector:pg16")
    assert services["redis"]["image"].startswith("redis:7")


@pytest.mark.parametrize("name", ["nginx", "api", "postgres", "redis", "minio"])
def test_core_services_have_healthcheck(services, name):
    """`docker compose up --wait` chỉ báo xong khi các dịch vụ này healthy."""
    assert "healthcheck" in services[name], f"{name} thiếu healthcheck"


def test_start_order_waits_for_healthy(services):
    assert services["nginx"]["depends_on"]["api"]["condition"] == "service_healthy"
    deps = services["api"]["depends_on"]
    for dep in ("postgres", "redis", "minio"):
        assert deps[dep]["condition"] == "service_healthy"


def test_host_ports_are_configurable(services):
    """Máy đã bận cổng 80 / 5432… đổi bằng biến môi trường (NGINX_PORT, POSTGRES_PORT…) thay vì sửa tệp."""
    for name, s in services.items():
        for port in s.get("ports", []):
            host = str(port).rsplit(":", 1)[0]
            assert host.startswith("${"), f"{name}: cổng host {port} chưa đổi được qua biến môi trường"


def test_stt_url_matches_container_port(services):
    """Trong mạng compose, gọi stt bằng cổng trong container, không phải cổng host."""
    from app.core.config import Settings

    container_port = str(services["stt"]["ports"][0]).rsplit(":", 1)[1]
    assert str(urlparse(Settings().stt_whisper_url).port) == container_port
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert f"STT_WHISPER_URL=http://stt:{container_port}" in env_example


def test_backend_services_mount_seed(services):
    for name in ("api", "worker", "beat"):
        assert any(str(v).startswith("./seed:/seed") for v in services[name].get("volumes", [])), name


def test_gitignore_ignores_claude_worktrees():
    lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".claude/worktrees/" in lines
