"""Khung test tích hợp (KT-03): pytest + httpx gọi API thật đang chạy (docker compose hoặc CI).

Mặc định BỎ QUA mọi test gắn `@pytest.mark.integration`. Bật bằng biến môi trường:

    RUN_INTEGRATION=1 INTEGRATION_API_URL=http://localhost:8000 uv run pytest -q -m integration

- `INTEGRATION_API_URL`: gốc API (mặc định http://localhost:8000 – cổng api của docker compose).
- Khi đã bật mà API không trả lời /health → test FAIL (không bỏ qua), để CI thấy stack hỏng.
- Test không gắn mark (vd. test_seed_data.py) vẫn chạy bình thường trong `pytest -q`.
"""

import os
from collections.abc import Iterator

import httpx
import pytest

RUN = os.getenv("RUN_INTEGRATION", "").lower() in {"1", "true", "yes"}
API_URL = os.getenv("INTEGRATION_API_URL", "http://localhost:8000").rstrip("/")
API_PREFIX = "/api/v1"
TIMEOUT = float(os.getenv("INTEGRATION_TIMEOUT", "10"))

_SKIP = pytest.mark.skip(reason="test tích hợp: đặt RUN_INTEGRATION=1 và chạy stack (docker compose up -d)")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if RUN:
        return
    for item in items:
        if item.get_closest_marker("integration"):
            item.add_marker(_SKIP)


@pytest.fixture(scope="session")
def api_url() -> str:
    return API_URL


@pytest.fixture(scope="session")
def http() -> Iterator[httpx.Client]:
    """Client tới gốc API (không có /api/v1) – dùng cho /health, /openapi.json."""
    with httpx.Client(base_url=API_URL, timeout=TIMEOUT) as c:
        try:
            c.get("/health").raise_for_status()
        except httpx.HTTPError as exc:
            pytest.fail(f"RUN_INTEGRATION=1 nhưng API {API_URL} không sẵn sàng: {exc}")
        yield c


@pytest.fixture(scope="session")
def api(http: httpx.Client) -> Iterator[httpx.Client]:
    """Client tới {API_URL}/api/v1 – đường dẫn trong test viết như Bảng 5.10 (vd. "/auth/login")."""
    with httpx.Client(base_url=API_URL + API_PREFIX, timeout=TIMEOUT) as c:
        yield c
