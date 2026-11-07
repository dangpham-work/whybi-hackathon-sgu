"""C1-02 – PUT /admin/ai-config: QTV đổi nhà cung cấp / model dự phòng lúc chạy (FR-AD-05)."""

from uuid import uuid4

import pytest

from app.ai import gateway as gw_mod
from app.api.deps import CurrentUser, get_current_user
from app.main import app
from app.models.enums import Role

BODY = {
    "llm": {
        "kind": "LLM",
        "provider": "openai_compat",
        "model": "qwen",
        "fallbackProvider": "gemini",
        "fallbackModel": "gemini-2.5-flash-lite",
    },
    "stt": {"kind": "STT", "provider": "cloud", "model": "default"},
    "tts": {"kind": "TTS", "provider": "cloud", "model": "default"},
}


@pytest.fixture
def as_role():
    def _set(role: Role):
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=uuid4(), role=role)

    yield _set
    app.dependency_overrides.pop(get_current_user, None)
    gw_mod.reset_gateway()


def test_admin_can_update_llm_config(client, as_role):
    as_role(Role.ADMIN)
    r = client.put("/api/v1/admin/ai-config", json=BODY)
    assert r.status_code == 200, r.text
    assert r.json()["llm"]["provider"] == "openai_compat"
    assert (
        gw_mod._override["provider"] == "openai_compat"
        and gw_mod._override["fallback_model"] == "gemini-2.5-flash-lite"
    )


def test_unknown_provider_rejected(client, as_role):
    as_role(Role.ADMIN)
    bad = {**BODY, "llm": {**BODY["llm"], "provider": "khong-co"}}
    r = client.put("/api/v1/admin/ai-config", json=bad)
    assert r.status_code == 422 and r.json()["error"]["code"] == "UNKNOWN_PROVIDER"
    assert gw_mod._override == {}


def test_non_admin_forbidden(client, as_role):
    as_role(Role.STUDENT)
    assert client.put("/api/v1/admin/ai-config", json=BODY).status_code == 403
