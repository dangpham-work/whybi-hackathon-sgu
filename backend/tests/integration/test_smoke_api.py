"""KT-03 – smoke tích hợp trên stack thật (api + postgres + redis). Bỏ qua khi không có RUN_INTEGRATION=1."""

import pytest

pytestmark = pytest.mark.integration


def test_health(http):
    res = http.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_openapi_co_prefix_api_v1(http):
    paths = http.get("/openapi.json").json()["paths"]
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/classes/{class_id}/tree" in paths


def test_loi_404_dung_dinh_dang_app_error(api):
    res = api.get("/khong-ton-tai")
    assert res.status_code == 404
    body = res.json()
    assert set(body["error"]) == {"code", "message", "details"}
    assert body["error"]["code"] == "NOT_FOUND"


def test_endpoint_can_dang_nhap_tra_401_khi_thieu_token(api):
    res = api.get("/me")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "UNAUTHORIZED"


def test_body_sai_tra_422_validation_error(api):
    res = api.post("/auth/login", json={"email": "khong-phai-email"})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.xfail(reason="C2-07: EmailStr trong api/auth.py chặn đuôi .test của tài khoản demo → 422", strict=False)
def test_dang_nhap_tai_khoan_demo_khong_bi_422(api):
    # seed/users.json + docs/demo-script.md dùng gv@whybi.test; email phải qua được bước kiểm schema
    res = api.post("/auth/login", json={"email": "gv@whybi.test", "password": "Whybi@2026"})
    assert res.status_code != 422
