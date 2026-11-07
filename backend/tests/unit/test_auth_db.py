"""C2-07 – đăng nhập qua bảng `users` thật. Chạy khi có TEST_DATABASE_URL (CSDL đã migrate); mọi ghi đều rollback."""

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.db.session import get_db
from app.main import app
from app.models.enums import Role
from app.models.users import User

DB_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="đặt TEST_DATABASE_URL để chạy trên Postgres thật")


@pytest.fixture
def api():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    engine = create_engine(DB_URL)
    conn = engine.connect()
    tx = conn.begin()
    db = Session(bind=conn, join_transaction_mode="create_savepoint")
    db.add(
        User(
            id=uuid4(),
            full_name="SV thử DB",
            email="Sv.Db@Whybi.Test",
            password_hash=hash_password("Whybi@2026"),
            role=Role.STUDENT,
        )
    )
    db.flush()
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    db.close()
    tx.rollback()
    conn.close()
    engine.dispose()


def _login(api):
    r = api.post("/api/v1/auth/login", json={"email": "sv.db@whybi.test", "password": "Whybi@2026"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['accessToken']}"}


def test_login_and_me_from_database(api):
    me = api.get("/api/v1/me", headers=_login(api)).json()
    assert me["fullName"] == "SV thử DB" and me["role"] == "STUDENT"


def test_update_profile_persists(api):
    h = _login(api)
    assert api.patch("/api/v1/me", headers=h, json={"fullName": "Tên mới"}).status_code == 200
    assert api.get("/api/v1/me", headers=h).json()["fullName"] == "Tên mới"
