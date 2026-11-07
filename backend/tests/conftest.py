import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("LLM_MODE", "fake")
os.environ.setdefault("LOG_JSON", "false")
os.environ.setdefault("ALLOW_DEV_TOKENS", "true")  # token dev-* tạm tới C2-07

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)
